from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.settings import get_settings
from backend.db.session import engine
from backend.app.routers.auth import router as auth_router
from backend.app.routers.visits import router as visits_router
from backend.app.routers.planning import router as planning_router
from backend.app.routers.admin import router as admin_router


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic could be added here (e.g., warm caches)
    yield
    # Ensure DB connections are cleanly closed on shutdown
    await engine.dispose()


def create_app(allowed_origins: Sequence[str] | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        allowed_origins: Optional list of CORS origins to allow. If not provided,
            permissive defaults will be used for local development.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

    cors_origins = list(
        allowed_origins
        or [
            "http://localhost",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(visits_router, prefix="/visits", tags=["visits"])
    app.include_router(planning_router, prefix="/planning", tags=["planning"])
    app.include_router(admin_router, prefix="/admin", tags=["admin"])

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

