from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models import Base

_settings = get_settings()
engine = create_async_engine(_settings.database_url, echo=False)

if "sqlite" in _settings.database_url:
    # WAL mode lets reads happen concurrently with writes — prevents "database is
    # locked" errors when multiple tabs run simultaneous analyses.
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA synchronous=NORMAL")
        dbapi_conn.execute("PRAGMA busy_timeout=5000")

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
