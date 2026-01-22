import asyncio
import sys
import os
from datetime import date

# Add current directory to sys.path so imports work
sys.path.append(os.getcwd())

from db.session import AsyncSessionLocal
from app.services.capacity_simulation_service import simulate_week_capacity
from app.models.availability import AvailabilityWeek
from sqlalchemy import select
import logging

# Configure logging to show INFO messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)


async def main():
    async with AsyncSessionLocal() as db:
        print("--- Checking AvailabilityWeek Data ---")

        # Count total users
        from app.models.user import User

        stmt = select(User)
        users = (await db.execute(stmt)).scalars().all()
        print(f"Total users in DB: {len(users)}")
        for u in users:
            print(
                f"  User: {u.id} - {u.full_name} (Roofvogel: {getattr(u, 'roofvogel', '?')})"
            )

        # Check availability for Week 18 using ORM select
        week = 18
        print(f"\n--- Checking Availability for Week {week} (ORM select) ---")
        stmt = select(AvailabilityWeek).where(AvailabilityWeek.week == week)
        rows = (await db.execute(stmt)).scalars().all()
        print(f"Found {len(rows)} AvailabilityWeek rows for Week {week}.")
        for r in rows:
            print(
                f"  Row: user_id={r.user_id}, morning={r.morning_days}, day={r.daytime_days}, night={r.nighttime_days}, flex={r.flex_days}"
            )

        # Check availability for Week 18 using Table select (as in service)
        print(f"\n--- Checking Availability for Week {week} (Table select) ---")
        stmt = AvailabilityWeek.__table__.select().where(AvailabilityWeek.week == week)
        # Note: .scalars() on Core result yields the first column (id)
        rows_core = (await db.execute(stmt)).scalars().all()
        print(f"Found {len(rows_core)} rows using Table select (scalars).")
        print(f"  First few scalars: {rows_core[:3]}")

        # Check without scalars to see what we get
        rows_raw = (await db.execute(stmt)).all()
        print(f"Found {len(rows_raw)} rows using Table select (raw).")
        if rows_raw:
            print(f"  First raw row: {rows_raw[0]}")
            print(
                f"  getattr(row, 'user_id'): {getattr(rows_raw[0], 'user_id', 'FAIL')}"
            )

        # Simulate for a specific week
        # 2025-W18 starts on Monday 2025-04-28
        week_monday = date(2025, 4, 28)
        print(
            f"\n--- Simulating for week starting {week_monday} (Week {week_monday.isocalendar().week}) ---"
        )

        result = await simulate_week_capacity(db, week_monday)

        if not result:
            print("No capacity results returned.")
        else:
            print("Simulation Result:")
            for family, parts in result.items():
                for part, cap in parts.items():
                    print(
                        f"  {family} - {part}: Required={cap.required}, Assigned={cap.assigned}, Shortfall={cap.shortfall}, Spare={cap.spare}"
                    )


if __name__ == "__main__":
    asyncio.run(main())
