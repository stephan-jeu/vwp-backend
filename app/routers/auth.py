from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()


@router.get("/me")
async def get_me() -> dict[str, str]:
    """Return basic info for the authenticated user placeholder."""
    return {"user": "placeholder"}
