from __future__ import annotations

import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.pvw_backfill_service import (  # noqa: E402
    backfill_visit_protocol_visit_windows,
)
from db.session import AsyncSessionLocal  # noqa: E402


async def run_backfill_script() -> None:
    """Run the PVW backfill process using an app session.

    Returns:
        None.
    """

    async with AsyncSessionLocal() as db:
        await backfill_visit_protocol_visit_windows(db)


if __name__ == "__main__":
    asyncio.run(run_backfill_script())
