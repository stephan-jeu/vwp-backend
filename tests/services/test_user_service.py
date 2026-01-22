import pytest
from fastapi import HTTPException

from app.models.user import User
from app.services.user_service import delete_user


@pytest.mark.asyncio
async def test_delete_user_soft_deletes_user_and_commits(mocker):
    # Arrange
    db = mocker.create_autospec("sqlalchemy.ext.asyncio.AsyncSession", instance=True)
    user = User(id=123, full_name="Cascade Test User", email="cascade@example.com")
    db.get = mocker.AsyncMock(return_value=user)
    db.commit = mocker.AsyncMock()

    soft_delete_entity = mocker.patch("app.services.user_service.soft_delete_entity")
    soft_delete_entity.return_value = mocker.AsyncMock()

    # Act
    await delete_user(db, user.id)

    # Assert
    db.get.assert_awaited_once_with(User, user.id)
    soft_delete_entity.assert_awaited_once_with(db, user, cascade=True)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_user_when_missing_raises_404(mocker):
    # Arrange
    db = mocker.create_autospec("sqlalchemy.ext.asyncio.AsyncSession", instance=True)
    db.get = mocker.AsyncMock(return_value=None)

    # Act / Assert
    with pytest.raises(HTTPException) as exc:
        await delete_user(db, 999)

    assert exc.value.status_code == 404
