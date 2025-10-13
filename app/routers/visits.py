from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()


@router.get("")
async def list_visits() -> list[dict[str, str]]:
    """List visits placeholder endpoint."""
    return []
