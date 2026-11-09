from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from procedurescout_core.db_url import sqlalchemy_url

if TYPE_CHECKING:
    from procedurescout_core.mailer import Sender


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_database_url: str = "postgresql+psycopg://ps_api:ps_api_dev@localhost:5432/procedurescout"
    environment: str = "development"
    # Where published Parquet files live (D-033): a folder, or s3://<bucket> for
    # Cloudflare R2 (D-048) with the endpoint and a READ-ONLY key below.
    price_store_dir: str = "price-store"
    price_store_endpoint: str = ""
    price_store_key_id: str = ""
    price_store_secret: str = ""
    # Review page (ADM-01): off unless both are set. Interim sign-in, MFA later (ADM-02).
    admin_token: str = ""
    admin_database_url: str = ""
    # Provider portal (D-050): off unless PORTAL_DATABASE_URL is set. The portal
    # role writes provider accounts, homepages, reviews and counts only.
    portal_database_url: str = ""
    # Secret for reviewer fingerprints (never stored with emails).
    portal_secret: str = ""
    # Public address of the website, used in emailed links.
    site_url: str = "http://localhost:3000"
    # Development only: return sign-in and review links in responses (there is
    # no email service yet, Q26). Always off when ENVIRONMENT=production.
    portal_dev_links: bool = False
    # Email (Q26): "resend" or "smtp"; nothing is sent until these are set.
    email_provider: str = ""
    email_from: str = ""
    resend_api_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    # Billing (D-051): off until Stripe keys are set and Cooper turns it on.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    # Hosting (D-048): instead of API_DATABASE_URL, give the owner DATABASE_URL
    # plus PS_API_PASSWORD and the API connects as the restricted role.
    database_url: str = ""
    ps_api_role: str = "ps_api"
    ps_api_password: str = ""
    ps_portal_role: str = "ps_portal"
    ps_portal_password: str = ""

    @model_validator(mode="after")
    def _api_url_from_parts(self) -> Settings:
        if (
            "api_database_url" not in self.model_fields_set
            and self.database_url
            and (self.ps_api_password)
        ):
            url = make_url(sqlalchemy_url(self.database_url)).set(
                username=self.ps_api_role, password=self.ps_api_password
            )
            self.api_database_url = url.render_as_string(hide_password=False)
        if (
            "portal_database_url" not in self.model_fields_set
            and self.database_url
            and (self.ps_portal_password)
        ):
            url = make_url(sqlalchemy_url(self.database_url)).set(
                username=self.ps_portal_role, password=self.ps_portal_password
            )
            self.portal_database_url = url.render_as_string(hide_password=False)
        return self

    @property
    def show_dev_links(self) -> bool:
        return self.portal_dev_links and self.environment != "production"

    def mail_sender(self) -> Sender | None:
        from procedurescout_core.mailer import sender_from

        return sender_from(
            self.email_provider,
            self.email_from,
            self.resend_api_key,
            self.smtp_host,
            self.smtp_port,
            self.smtp_username,
            self.smtp_password,
        )

    def store_args(self) -> tuple[str, str, str, str]:
        return (
            self.price_store_dir,
            self.price_store_endpoint,
            self.price_store_key_id,
            self.price_store_secret,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
