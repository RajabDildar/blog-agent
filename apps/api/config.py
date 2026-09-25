"""FastAPI application settings and environment configuration."""
import os
from functools import lru_cache
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment or .env file."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgrespassword@localhost:5432/blog_agent"
    TEST_DATABASE_URL: str = "postgresql+psycopg://postgres:postgrespassword@localhost:5432/blog_agent_test"
    GOOGLE_CLIENT_ID: str = "mock-google-client-id"
    SESSION_SECRET_KEY: str = "dev_session_secret_key_12345678901234567890"
    SESSION_MAX_AGE_SECONDS: int = 7 * 24 * 3600  # 7 days
    ALLOWED_ORIGINS: Union[str, List[str]] = ["http://localhost:5173", "http://localhost:3000"]
    ENVIRONMENT: str = "development"

    # Phase 4: Queue, Checkpointing, Quotas & Abuse Prevention
    REDIS_URL: str = "redis://localhost:6379/0"
    CHECKPOINT_BACKEND: str = "postgres"
    AUTHENTICATED_DAILY_RUN_LIMIT: int = 5
    ANONYMOUS_DAILY_IP_LIMIT: int = 5
    INTENT_REQUESTS_PER_IP_PER_HOUR: int = 20
    ANONYMOUS_RETENTION_HOURS: int = 48


    SESSION_COOKIE_NAME: str = "blog_session"
    CSRF_COOKIE_NAME: str = "blog_csrf"
    ANONYMOUS_COOKIE_NAME: str = "blog_anon"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def cookie_secure(self) -> bool:
        """In production, enforce Secure flag on cookies."""
        return self.is_production


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
