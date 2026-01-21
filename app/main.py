from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.settings import get_settings
from db.session import engine
from app.routers.auth import router as auth_router
from app.routers.visits import router as visits_router
from app.routers.clusters import router as clusters_router
from app.routers.planning import router as planning_router
from app.routers.projects import router as projects_router
from app.routers.admin import router as admin_router
from app.routers.admin_availability import router as admin_availability_router

import logging

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic could be added here (e.g., warm caches)
    yield
    # Ensure DB connections are cleanly closed on shutdown
    await engine.dispose()


# cmd uvicorn app.main:app --reload
def create_app(allowed_origins: Sequence[str] | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        allowed_origins: Optional list of CORS origins to allow. If not provided,
            permissive defaults will be used for local development.

    Returns:
        Configured FastAPI application.
    """
    logging.getLogger("uvicorn.error").setLevel(logging.DEBUG)

    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

    cors_origins = list(
        allowed_origins
        or [
            "http://localhost",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "https://vwp.onrender.com",
            "https://viridis-demo.nextaimove.com",
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
    app.include_router(projects_router, prefix="/projects", tags=["projects"])
    app.include_router(admin_router, prefix="/admin", tags=["admin"])
    app.include_router(admin_availability_router, prefix="/admin", tags=["admin"])
    app.include_router(clusters_router, prefix="/clusters", tags=["clusters"])

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
