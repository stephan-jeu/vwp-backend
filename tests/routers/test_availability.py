import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.models.user import User
from app.models.availability import AvailabilityWeek
from app.services.security import get_current_user
from db.session import get_db

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_db_session():
    return AsyncMock()


@pytest.fixture
def test_user():
    return User(id=123, email="test@example.com", admin=False)


@pytest.fixture
def override_deps(app, test_user, mock_db_session):
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db] = lambda: mock_db_session
    yield
    app.dependency_overrides = {}


async def test_get_my_availability_unauthorized(async_client: AsyncClient, app):
    # No dependency overrides here
    # Mock get_db though to avoid connection errors if it tries
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    
    # We expect 401 because we didn't override get_current_user
    # AND we didn't provide a valid token header.
    # Note: depends on get_current_user implementation -> it verifies token.
    # If no token, it raises 401.
    response = await async_client.get("/availability/me")
    assert response.status_code == 401


async def test_get_my_availability_empty(
    async_client: AsyncClient, 
    override_deps, 
    mocker
):
    # Mock the service function directly to return empty list
    mocker.patch(
        "app.routers.availability.get_user_availability",
        return_value=[]
    )
    
    response = await async_client.get("/availability/me")
    assert response.status_code == 200
    assert response.json() == []


async def test_get_my_availability_with_data(
    async_client: AsyncClient,
    override_deps,
    mocker,
    test_user
):
    # Mock data
    week1 = AvailabilityWeek(
        id=1,
        user_id=test_user.id,
        week=10,
        morning_days=2,
        daytime_days=1,
        nighttime_days=0,
        flex_days=3,
    )
    week2 = AvailabilityWeek(
        id=2,
        user_id=test_user.id,
        week=11,
        morning_days=0,
        daytime_days=0,
        nighttime_days=0,
        flex_days=0,
    )
    
    # Patch service
    mocker.patch(
        "app.routers.availability.get_user_availability",
        return_value=[week1, week2]
    )

    response = await async_client.get("/availability/me")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    
    # Sort to ensure order
    data.sort(key=lambda x: x["week"])
    
    assert data[0]["week"] == 10
    assert data[0]["morning_days"] == 2
    assert data[0]["flex_days"] == 3
    
    assert data[1]["week"] == 11
    assert data[1]["morning_days"] == 0


async def test_get_my_availability_pass_params(
    async_client: AsyncClient,
    override_deps,
    mocker
):
    mock_service = mocker.patch(
        "app.routers.availability.get_user_availability",
        return_value=[]
    )

    await async_client.get("/availability/me", params={"week_start": 20, "week_end": 25})
    
    # verify service called with correct args
    mock_service.assert_called_once()
    call_kwargs = mock_service.call_args.kwargs
    assert call_kwargs["week_start"] == 20
    assert call_kwargs["week_end"] == 25
