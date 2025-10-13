from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()


@router.get("")
async def get_planning() -> dict[str, str]:
    """Return planning placeholder."""
    return {"planning": "placeholder"}
