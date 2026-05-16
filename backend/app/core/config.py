"""Application settings — loaded from environment (see .env.example)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # NemoClaw / orchestrator route — planning model (see docs/HACKATHON_ENV.md; env name kept NEMCLAW_MODEL).
    nemoclaw_model: str = Field(default="nemoclaw", validation_alias="NEMCLAW_MODEL")

    # Lightweight tier: fast/cheap model IDs for search-adjacent LLM calls (queued, bounded parallelism).
    lightweight_model: str = Field(
        default="lightweight-search",
        validation_alias="LIGHTWEIGHT_MODEL",
    )
    light_queue_max_parallel: int = Field(
        default=4,
        validation_alias="LIGHT_QUEUE_MAX_PARALLEL",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
