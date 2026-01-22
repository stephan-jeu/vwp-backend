import asyncio
import sys
from sqlalchemy import text
from db.session import engine

# Add the parent directory to sys.path to allow imports from app/core/db
# This might be needed if running as a script directly
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))


async def truncate_planning_data():
    """
    Truncates planning-related tables in the database.
    WARNING: This will permanently delete data!
    """
    # Define tables to truncate in a safe order (though CASCADE handles most deps)
    tables = [
        "visit_functions",
        "visit_species",
        "visit_researchers",
        "visit_protocol_visit_windows",
        "visits",
        "activity_logs",
        "clusters",
        "projects",
    ]

    print("⚠️  WARNING: This script will TRUNCATE the following tables:")
    for t in tables:
        print(f"  - {t}")
    print("\nThis action is irreversible.")

    # Simple confirmation
    confirm = input("Type 'yes' to proceed: ")
    if confirm != "yes":
        print("Aborted.")
        return

    async with engine.begin() as conn:
        print("\nStarting truncation...")
        for table in tables:
            print(f"Truncating {table}...")
            # RESTART IDENTITY resets auto-increment counters
            # CASCADE deletes dependent rows in other tables (though we try to list them all)
            await conn.execute(
                text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;")
            )
        print("✅ Done.")


if __name__ == "__main__":
    try:
        asyncio.run(truncate_planning_data())
    except KeyboardInterrupt:
        print("\nCancelled.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
