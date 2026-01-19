
import pytest
from datetime import date
from sqlalchemy import select, and_
from app.models.user import User
from app.models.availability import AvailabilityWeek
from app.services.user_service import delete_user
from db.session import get_db

@pytest.fixture
async def db_session():
    async for session in get_db():
        yield session

@pytest.mark.asyncio
async def test_delete_user_cascades_availability(db_session):
    # 1. Create User and Availability
    user = User(full_name="Cascade Test User", email="cascade@example.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    
    # Use a random week to avoid collisions
    import random
    w = random.randint(1000, 2000)
    avail = AvailabilityWeek(user_id=user.id, week=w, morning_days=1)
    db_session.add(avail)
    await db_session.commit()
    await db_session.refresh(avail)
    
    # 2. Delete User
    # This currently calls cascade=False
    await delete_user(db_session, user.id)
    
    # 3. reload avail
    # We must clear session or refetch to see DB state
    await db_session.refresh(avail)
    
    # 4. Assertions
    # User should be deleted
    assert user.deleted_at is not None, "User should be soft-deleted"
    
    # Availability should also be deleted if cascade works
    # Currently expected to FAIL (be None) if cascade=False
    assert avail.deleted_at is not None, "Availability should be soft-deleted via cascade"
