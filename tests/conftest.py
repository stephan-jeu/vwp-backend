import asyncio
import os
import sys
from pathlib import Path
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

# Ensure the backend directory is importable so `app.*` modules resolve
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.main import create_app


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
