from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_database_url: str = "postgresql+psycopg://ps_api:ps_api_dev@localhost:5432/procedurescout"
    environment: str = "development"
    # Folder holding published Parquet files (D-033); an S3-compatible store later.
    price_store_dir: str = "price-store"
    # Review page (ADM-01): off unless both are set. Interim sign-in, MFA later (ADM-02).
    admin_token: str = ""
    admin_database_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
