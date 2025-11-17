import asyncio
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

# Ensure the backend directory is importable so `app.*` modules resolve
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    """Ensure the database schema is up-to-date for tests.

    Runs Alembic upgrade to head before any tests execute. This is necessary
    when models gained new columns (e.g., deleted_at) that tests rely on.
    """
    from alembic.config import Config
    from alembic import command

    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture()
def settings_override(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("DB_ECHO", "false")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://testserver/auth/callback")
    yield


@pytest.fixture()
def app(settings_override) -> FastAPI:
    return create_app()


@pytest.fixture()
async def async_client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# Lightweight fallback for pytest-mock's 'mocker' fixture when the plugin isn't loaded
@pytest.fixture()
def mocker():
    from unittest.mock import (
        AsyncMock,
        create_autospec as _create_autospec,
        MagicMock,
        Mock,
        patch,
    )

    class _SimpleMocker:
        def __init__(self):
            self._patchers: list = []
            # expose common unittest.mock helpers as attributes
            self.AsyncMock = AsyncMock
            self.MagicMock = MagicMock
            self.Mock = Mock
            self.create_autospec = _create_autospec

        def patch(self, target: str, *args, **kwargs):
            p = patch(target, *args, **kwargs)
            mocked = p.start()
            self._patchers.append(p)
            return mocked

    m = _SimpleMocker()
    try:
        yield m
    finally:
        for p in reversed(m._patchers):
            p.stop()
