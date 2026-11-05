from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_database_url: str = "postgresql+psycopg://ps_api:ps_api_dev@localhost:5432/procedurescout"
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
