from __future__ import annotations

import os
from pydantic import BaseModel, Field, SecretStr
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    # App
    app_name: str = Field(default="Veldwerkplanning API")
    debug: bool = Field(default=False)

    # Seasonal planner scheduler
    season_planner_scheduler_enabled: bool = Field(
        default_factory=lambda: os.getenv(
            "SEASON_PLANNER_SCHEDULER_ENABLED", "true"
        ).lower()
        in {"1", "true", "yes"}
    )
    season_planner_cron: str = Field(
        default_factory=lambda: os.getenv("SEASON_PLANNER_CRON", "0 2 * * *")
    )
    season_planner_timezone: str = Field(
        default_factory=lambda: os.getenv("SEASON_PLANNER_TIMEZONE", "Europe/Amsterdam")
    )

    # PVW backfill scheduler
    pvw_backfill_scheduler_enabled: bool = Field(
        default_factory=lambda: os.getenv(
            "PVW_BACKFILL_SCHEDULER_ENABLED", "true"
        ).lower()
        in {"1", "true", "yes"}
    )
    pvw_backfill_cron: str = Field(
        default_factory=lambda: os.getenv("PVW_BACKFILL_CRON", "30 2 * * *")
    )
    pvw_backfill_timezone: str = Field(
        default_factory=lambda: os.getenv("PVW_BACKFILL_TIMEZONE", "Europe/Amsterdam")
    )

    # Test mode
    test_mode_enabled: bool = Field(
        default_factory=lambda: os.getenv("TEST_MODE_ENABLED", "true").lower()
        in {"1", "true", "yes"}
    )

    # Database (asyncpg + SQLAlchemy)
    db_user: str = Field(default_factory=lambda: os.getenv("POSTGRES_USER", "postgres"))
    db_password: SecretStr = Field(
        default_factory=lambda: SecretStr(os.getenv("POSTGRES_PASSWORD", "postgres"))
    )
    db_host: str = Field(
        default_factory=lambda: os.getenv("POSTGRES_HOST", "localhost")
    )
    db_port: int = Field(
        default_factory=lambda: int(os.getenv("POSTGRES_PORT", "5432"))
    )
    db_name: str = Field(default_factory=lambda: os.getenv("POSTGRES_DB", "habitus"))
    db_echo: bool = Field(
        default_factory=lambda: os.getenv("DB_ECHO", "false").lower()
        in {"1", "true", "yes"}
    )
    db_pool_size: int = Field(
        default_factory=lambda: int(os.getenv("DB_POOL_SIZE", "5"))
    )
    db_max_overflow: int = Field(
        default_factory=lambda: int(os.getenv("DB_MAX_OVERFLOW", "10"))
    )

    # OAuth2 - Google
    google_client_id: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_CLIENT_ID", "")
    )
    google_client_secret: SecretStr = Field(
        default_factory=lambda: SecretStr(os.getenv("GOOGLE_CLIENT_SECRET", ""))
    )
    google_redirect_uri: str = Field(
        default_factory=lambda: os.getenv(
            "GOOGLE_REDIRECT_URI", "http://localhost:3000/auth/callback"
        )
    )

    # JWT
    jwt_secret: SecretStr = Field(
        default_factory=lambda: SecretStr(
            os.getenv("JWT_SECRET", "dev-insecure-secret")
        )
    )
    jwt_algorithm: str = Field(
        default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256")
    )
    access_token_expires_minutes: int = Field(
        default_factory=lambda: int(os.getenv("ACCESS_TOKEN_EXPIRES_MINUTES", "30"))
    )
    refresh_token_expires_days: int = Field(
        default_factory=lambda: int(os.getenv("REFRESH_TOKEN_EXPIRES_DAYS", "30"))
    )

    # google maps
    google_maps_api_key: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_MAPS_API_KEY", "")
    )

    @property
    def sqlalchemy_database_uri_async(self) -> str:
        # postgresql+asyncpg://user:pass@host:port/db
        pwd = self.db_password.get_secret_value()
        return f"postgresql+asyncpg://{self.db_user}:{pwd}@{self.db_host}:{self.db_port}/{self.db_name}"


def get_settings() -> Settings:
    # Keep a simple module-level singleton without extra deps
    # Evaluated only once per process
    global _SETTINGS_SINGLETON
    try:
        return _SETTINGS_SINGLETON
    except NameError:
        _SETTINGS_SINGLETON = Settings()  # type: ignore[reportPrivateUsage]
        return _SETTINGS_SINGLETON
