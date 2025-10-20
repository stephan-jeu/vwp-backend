import pytest


@pytest.mark.asyncio
async def test_login_google_returns_authorization_url(async_client):
    # Arrange

    # Act
    resp = await async_client.get("/auth/login")

    # Assert
    assert resp.status_code == 200
    data = resp.json()
    assert "authorization_url" in data
    assert "accounts.google.com" in data["authorization_url"]


@pytest.mark.asyncio
async def test_me_requires_bearer_token(async_client):
    # Arrange

    # Act
    resp = await async_client.get("/auth/me")

    # Assert
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_sub_when_valid(async_client, app, mocker):
    # Arrange
    from app.services.security import get_current_user

    class DummyUser:
        def __init__(self, email: str, admin: bool = False) -> None:
            self.email = email
            self.admin = admin

    app.dependency_overrides[get_current_user] = lambda: DummyUser(
        "user@example.com", False
    )
    headers = {"Authorization": "Bearer testtoken"}

    # Act
    resp = await async_client.get("/auth/me", headers=headers)

    # Assert
    assert resp.status_code == 200
    assert resp.json() == {"sub": "user@example.com", "admin": False}

    # Cleanup override
    app.dependency_overrides.clear()
