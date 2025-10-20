import pytest
from types import SimpleNamespace
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.security import assert_admin


@pytest.mark.asyncio
async def test_assert_admin_allows_admin(mocker):
    # Arrange
    user = SimpleNamespace(admin=True)
    result = SimpleNamespace(scalar_one_or_none=lambda: user)
    db = mocker.create_autospec(AsyncSession)
    db.execute = mocker.AsyncMock(return_value=result)

    # Act / Assert (no exception)
    await assert_admin(db, "admin@example.com")


@pytest.mark.asyncio
async def test_assert_admin_denies_non_admin(mocker):
    # Arrange
    user = SimpleNamespace(admin=False)
    result = SimpleNamespace(scalar_one_or_none=lambda: user)
    db = mocker.create_autospec(AsyncSession)
    db.execute = mocker.AsyncMock(return_value=result)

    # Act
    with pytest.raises(Exception):
        await assert_admin(db, "user@example.com")

