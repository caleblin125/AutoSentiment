import logging
import signal
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
