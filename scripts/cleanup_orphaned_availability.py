
import asyncio
import sys
from pathlib import Path
from sqlalchemy import select, update, and_
from datetime import datetime, timezone

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.user import User
from app.models.availability import AvailabilityWeek
from db.session import AsyncSessionLocal

async def cleanup_orphans():
    async with AsyncSessionLocal() as db:
        print("Checking for orphaned availability records...")
        
        # Find availability records where:
        # 1. User is deleted
        # 2. Availability is NOT deleted
        stmt = (
            select(AvailabilityWeek)
            .join(User, AvailabilityWeek.user_id == User.id)
            .where(
                and_(
                    User.deleted_at.is_not(None),
                    AvailabilityWeek.deleted_at.is_(None)
                )
            )
        )
        
        orphans = (await db.execute(stmt)).scalars().all()
        
        if not orphans:
            print("No orphans found! Database is clean.")
            return

        print(f"Found {len(orphans)} orphaned availability records.")
        
        orphans_ids = [o.id for o in orphans]
        now = datetime.now(timezone.utc)
        
        # Bulk soft-delete
        upd_stmt = (
            update(AvailabilityWeek)
            .where(AvailabilityWeek.id.in_(orphans_ids))
            .values(deleted_at=now)
        )
        
        await db.execute(upd_stmt)
        await db.commit()
        print("Successfully cleaned up orphans.")

if __name__ == "__main__":
    asyncio.run(cleanup_orphans())
