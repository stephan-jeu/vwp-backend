from __future__ import annotations

import os
from pydantic import BaseModel, Field, SecretStr


class Settings(BaseModel):
    # App
    app_name: str = Field(default="Veldwerkplanning API")
    debug: bool = Field(default=False)

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
    db_name: str = Field(default_factory=lambda: os.getenv("POSTGRES_DB", "vwp"))
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
