from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Subscription SaaS"
    environment: str = "local"
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/subscriptions"

    jwt_secret_key: str = Field(default="change-me-in-production")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    auth_cookie_name: str = "access_token"
    cookie_secure: bool = False

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_success_url: AnyHttpUrl | str = "http://localhost:8000/subscription/success"
    stripe_cancel_url: AnyHttpUrl | str = "http://localhost:8000/plans"
    stripe_price_starter_weekly: str = ""
    stripe_price_starter_monthly: str = ""
    stripe_price_pro_weekly: str = ""
    stripe_price_pro_monthly: str = ""

    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
