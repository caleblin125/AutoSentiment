import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.orchestrator import recover_stale_runs
from app.api.routes import router as api_router
from app.core.config import get_settings
from app.db.session import create_tables

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await create_tables()
    recovered = await recover_stale_runs()
    if recovered:
        logger.info("Recovered %d stale runs on startup", recovered)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AutoSentiment API", lifespan=lifespan)
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
