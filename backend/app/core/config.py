from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Tests and local scripts should be able to pass Python field names
        # while production still reads the uppercase env aliases.
        populate_by_name=True,
    )

    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    ollama_base_url: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_BASE_URL")

    # 120B — query expansion and final synthesis
    nemoclaw_model: str = Field(default="nemotron-3-super", validation_alias="NEMCLAW_MODEL")
    # 30B — per-item sentiment (queued, bounded parallelism)
    lightweight_model: str = Field(default="nemotron-3-nano", validation_alias="LIGHTWEIGHT_MODEL")
    light_queue_max_parallel: int = Field(default=4, validation_alias="LIGHT_QUEUE_MAX_PARALLEL")

    brave_api_key: str = Field(default="", validation_alias="BRAVE_API_KEY")
    max_queries_per_run: int = Field(default=16, validation_alias="MAX_QUERIES_PER_RUN")
    max_urls_per_run: int = Field(default=30, validation_alias="MAX_URLS_PER_RUN")
    max_items_per_run: int = Field(default=100, validation_alias="MAX_ITEMS_PER_RUN")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
