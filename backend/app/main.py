import asyncio
import logging
import signal
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete

from app.agents.orchestrator import recover_stale_runs
from app.api.routes import router as api_router
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal, create_tables

logger = logging.getLogger(__name__)

_CACHE_TTL_DAYS = 7


async def _warmup_model(base_url: str, model: str) -> None:
    """Send a tiny prompt to pre-load a model into GPU VRAM.

    Uses the non-streaming Ollama API with a minimal payload so the model
    weights are mapped before the first real user request arrives.
    Errors are logged but never propagated — warm-up is best-effort.
    """
    import httpx
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(
                f"{base_url.rstrip('/')}/api/generate",
                json={"model": model, "prompt": "hi", "stream": False, "keep_alive": "10m"},
            )
            r.raise_for_status()
        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info("Warmed up model %s in %d ms", model, elapsed)
    except Exception as exc:
        logger.warning("Warm-up failed for model %s: %s", model, exc)


async def _warmup_all_models() -> None:
    """Fire parallel warm-up requests for all configured Ollama models."""
    settings = get_settings()
    models = {settings.nemoclaw_model, settings.lightweight_model, settings.suggestion_model}
    await asyncio.gather(
        *(_warmup_model(settings.ollama_base_url, m) for m in models),
        return_exceptions=True,
    )


async def _evict_stale_cache() -> int:
    from app.models import FetchedURLCache
    cutoff = datetime.now(UTC) - timedelta(days=_CACHE_TTL_DAYS)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(FetchedURLCache).where(FetchedURLCache.created_at < cutoff)
        )
        await db.commit()
        return result.rowcount  # type: ignore[return-value]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await create_tables()
    recovered = await recover_stale_runs()
    if recovered:
        logger.info("Recovered %d stale runs on startup", recovered)
    evicted = await _evict_stale_cache()
    if evicted:
        logger.info("Evicted %d stale URL cache entries (>%d days old)", evicted, _CACHE_TTL_DAYS)

    # Kick off model warm-up in the background — doesn't block server startup.
    asyncio.create_task(_warmup_all_models())

    # Graceful shutdown: cancel all active runs on SIGTERM/SIGINT.
    from app.api import event_bus
    shutdown_event = event_bus._shutdown

    async def _handle_shutdown():
        await shutdown_event.wait()
        logger.info("Shutting down — cancelling active SSE queues")
        event_bus.shutdown_all()

    import asyncio
    shutdown_task = asyncio.create_task(_handle_shutdown())

    yield

    shutdown_task.cancel()
    try:
        await shutdown_task
    except asyncio.CancelledError:
        pass

    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AutoSentiment API",
        description="Multi-source public sentiment intelligence — search, fetch, analyze, and synthesize web opinion at scale.",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api")
    return app


app = create_app()
