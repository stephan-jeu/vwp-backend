from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Sequence

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from core.settings import get_settings
from db.session import engine, AsyncSessionLocal
from app.routers.auth import router as auth_router
from app.routers.visits import router as visits_router
from app.routers.clusters import router as clusters_router
from app.routers.planning import router as planning_router
from app.routers.projects import router as projects_router
from app.routers.admin import router as admin_router
from app.routers.admin_availability import router as admin_availability_router
from app.routers.availability import router as availability_router
from app.services.season_planner_scheduler import (
    shutdown_season_planner_scheduler,
    start_season_planner_scheduler,
)
from app.services.pvw_backfill_scheduler import (
    shutdown_pvw_backfill_scheduler,
    start_pvw_backfill_scheduler,
)
from app.services.trash_purge_scheduler import (
    shutdown_trash_purge_scheduler,
    start_trash_purge_scheduler,
)

import logging

settings = get_settings()

if settings.sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.tenant_name,
        traces_sample_rate=1.0,
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic could be added here (e.g., warm caches)
    start_season_planner_scheduler()
    start_pvw_backfill_scheduler()
    start_trash_purge_scheduler()
    yield
    # Ensure DB connections are cleanly closed on shutdown
    shutdown_season_planner_scheduler()
    shutdown_pvw_backfill_scheduler()
    shutdown_trash_purge_scheduler()
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
    import os

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    
    # Force uvicorn loggers to use the same config by propagating to root
    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        logger = logging.getLogger(logger_name)
        logger.handlers = []
        logger.propagate = True
        logger.setLevel(log_level)

    # Silence noisy libraries even in DEBUG mode
    for logger_name in ["httpx", "httpcore", "hpack"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

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
            "https://habitus-vwp.nextaimove.com",
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
    app.include_router(availability_router, prefix="/availability", tags=["availability"])
    from app.routers.availability_patterns import router as availability_patterns_router
    app.include_router(availability_patterns_router, prefix="/api", tags=["availability_patterns"])
    from app.routers.user_unavailabilities import router as unavailabilities_router
    app.include_router(unavailabilities_router, prefix="/api", tags=["user_unavailabilities"])
    app.include_router(clusters_router, prefix="/clusters", tags=["clusters"])

    @app.get("/health")
    async def health() -> dict[str, str]:
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
        except Exception as e:
            logging.error(f"Health check failed (Database connect error): {e}")
            raise HTTPException(
                status_code=503,
                detail={"status": "error", "database": "down"},
            )
        return {"status": "ok", "database": "up"}

    return app


app = create_app()
