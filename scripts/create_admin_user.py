from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import NoReturn

from sqlalchemy import select

# Ensure the backend root (parent of this file's directory) is on sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.session import AsyncSessionLocal
from app.models.user import User


async def _ensure_admin(email: str) -> None:
    """Create or update an admin user with the given email.

    Args:
        email: Email address of the admin user to upsert.

    Returns:
        None. Commits changes to the database.
    """

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        user: User | None = result.scalar_one_or_none()

        if user is None:
            user = User(email=email, admin=True)
            session.add(user)
            await session.commit()
            print(f"Created admin user: {email}")
            return

        if not user.admin:
            user.admin = True
            await session.commit()
            print(f"Updated user to admin: {email}")
        else:
            print(f"User already admin: {email}")


def main() -> NoReturn:
    """Entry point for creating/updating the admin user."""
    asyncio.run(_ensure_admin("stephan@nextaimove.com"))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
