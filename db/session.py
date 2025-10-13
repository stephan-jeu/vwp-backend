from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.core.settings import get_settings


settings = get_settings()

# Using NullPool by default for compatibility across local/dev; adjust if you prefer QueuePool.
engine = create_async_engine(
    settings.sqlalchemy_database_uri_async,
    echo=settings.db_echo,
    poolclass=NullPool if settings.debug else None,  # use default pool in non-debug
    pool_size=None if settings.debug else settings.db_pool_size,
    max_overflow=None if settings.debug else settings.db_max_overflow,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            # session is context-managed; explicit close is handled
            # Leaving this block for clarity or additional cleanup if needed
            pass
