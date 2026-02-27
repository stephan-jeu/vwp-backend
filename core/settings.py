from __future__ import annotations

import os
from pydantic import BaseModel, Field, SecretStr
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    # App
    app_name: str = Field(default="Veldwerkplanning API")
    debug: bool = Field(default=False)
    frontend_url: str = Field(
        default_factory=lambda: os.getenv("FRONTEND_URL", "http://localhost:3000")
    )

    # Multi-tenancy & Feature Flags
    tenant_name: str = Field(
        default_factory=lambda: os.getenv("TENANT_NAME", "Habitus")
    )
    
    # Feature: Daily Planning (Granular Day Assignments)
    feature_daily_planning: bool = Field(
        default_factory=lambda: os.getenv("FEATURE_DAILY_PLANNING", "false").lower() in {"1", "true", "yes"}
    )
    
    # Feature: Strict Availability (Specific Day Restrictions)
    feature_strict_availability: bool = Field(
        default_factory=lambda: os.getenv("FEATURE_STRICT_AVAILABILITY", "false").lower() in {"1", "true", "yes"}
    )

    # Feature: Advertise (Hulp gevraagd / Vraag iemand anders)
    feature_advertise: bool = Field(
        default_factory=lambda: os.getenv("FEATURE_ADVERTISE", "true").lower() in {"1", "true", "yes"}
    )

    # Feature: Visit Code (Condensed species/function/daypart codes on visits)
    enable_visit_code: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_VISIT_CODE", "false").lower() in {"1", "true", "yes"}
    )
    
    # Feature: Auth Providers (google, azure_ad, email)
    auth_providers: list[str] = Field(
        default_factory=lambda: [
            p.strip() for p in os.getenv("AUTH_PROVIDERS", "google").split(",")
        ]
    )
    
    # Observability
    sentry_dsn: str | None = Field(
        default_factory=lambda: os.getenv("SENTRY_DSN")
    )
    
    # Constraint: English/Dutch Teaming (English speakers need Dutch buddy)
    constraint_english_dutch_teaming: bool = Field(
        default_factory=lambda: os.getenv("CONSTRAINT_ENGLISH_DUTCH_TEAMING", "false").lower() in {"1", "true", "yes"}
    )

    # Constraint: Large Team Penalty (Avoid >2 researchers per visit if possible)
    constraint_large_team_penalty: bool = Field(
        default_factory=lambda: os.getenv("CONSTRAINT_LARGE_TEAM_PENALTY", "true").lower() in {"1", "true", "yes"}
    )

    # Constraint: Max Travel Time (Minutes)
    constraint_max_travel_time_minutes: int = Field(
        default_factory=lambda: int(os.getenv("CONSTRAINT_MAX_TRAVEL_TIME_MINUTES", "75"))
    )

    # Constraint: Consecutive Travel Penalty
    constraint_consecutive_travel_penalty: bool = Field(
        default_factory=lambda: os.getenv("CONSTRAINT_CONSECUTIVE_TRAVEL_PENALTY", "true").lower() in {"1", "true", "yes"}
    )
    constraint_consecutive_travel_penalty_weight: int = Field(
        default_factory=lambda: int(os.getenv("CONSTRAINT_CONSECUTIVE_TRAVEL_PENALTY_WEIGHT", "1"))
    )

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
    season_planner_timeout_quick_seconds: float = Field(
        default_factory=lambda: float(
            os.getenv("SEASON_PLANNER_TIMEOUT_QUICK_SECONDS", "60")
        )
    )
    season_planner_timeout_thorough_seconds: float = Field(
        default_factory=lambda: float(
            os.getenv("SEASON_PLANNER_TIMEOUT_THOROUGH_SECONDS", "180")
        )
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

    # Trash purge scheduler
    trash_purge_scheduler_enabled: bool = Field(
        default_factory=lambda: os.getenv(
            "TRASH_PURGE_SCHEDULER_ENABLED", "true"
        ).lower()
        in {"1", "true", "yes"}
    )
    trash_purge_cron: str = Field(
        default_factory=lambda: os.getenv("TRASH_PURGE_CRON", "0 3 * * *")
    )
    trash_purge_timezone: str = Field(
        default_factory=lambda: os.getenv("TRASH_PURGE_TIMEZONE", "Europe/Amsterdam")
    )
    trash_purge_retention_days: int = Field(
        default_factory=lambda: int(os.getenv("TRASH_PURGE_RETENTION_DAYS", "30"))
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

    # OAuth2 - MS365
    ms365_client_id: str = Field(
        default_factory=lambda: os.getenv("MS365_CLIENT_ID", "")
    )
    ms365_client_secret: SecretStr = Field(
        default_factory=lambda: SecretStr(os.getenv("MS365_CLIENT_SECRET", ""))
    )
    ms365_tenant_id: str = Field(
        default_factory=lambda: os.getenv("MS365_TENANT_ID", "common")
    )
    ms365_redirect_uri: str = Field(
        default_factory=lambda: os.getenv(
            "MS365_REDIRECT_URI", "http://localhost:3000/auth/callback-ms365"
        )
    )

    # Auth Features
    enable_email_login: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_EMAIL_LOGIN", "false").lower() in {"1", "true", "yes"}
    )
    enable_ms365_login: bool = Field(
        default_factory=lambda: os.getenv("ENABLE_MS365_LOGIN", "false").lower() in {"1", "true", "yes"}
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

    smtp_host: str = Field(default_factory=lambda: os.getenv("SMTP_HOST", ""))
    smtp_port: int = Field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: str = Field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: SecretStr = Field(
        default_factory=lambda: SecretStr(os.getenv("SMTP_PASSWORD", ""))
    )
    admin_email: str = Field(default_factory=lambda: os.getenv("ADMIN_EMAIL", ""))

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
