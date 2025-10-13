from __future__ import annotations

from fastapi import APIRouter


router = APIRouter()


@router.get("")
async def admin_status() -> dict[str, str]:
    """Return admin status placeholder."""
    return {"status": "admin-ok"}

