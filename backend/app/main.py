"""FastAPI entrypoint — wire routers, CORS, and lifespan hooks here."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # TODO: create tables, warm caches, etc. (see app/db/IMPLEMENTATION.md)
    yield
    # TODO: dispose engine / close connections if needed


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
