import pytest
from fastapi import FastAPI, status


@pytest.mark.asyncio
async def test_list_projects_requires_admin(async_client):
    # Act
    resp = await async_client.get("/projects")

    # Assert
    assert (
        resp.status_code == status.HTTP_401_UNAUTHORIZED
        or resp.status_code == status.HTTP_403_FORBIDDEN
    )


@pytest.mark.asyncio
async def test_create_update_delete_project_flow(async_client, app, mocker):
    # Arrange: bypass admin guard by patching require_admin to a no-op
    from app.services.security import require_admin

    app.dependency_overrides[require_admin] = lambda: None

    # Create
    payload = {
        "code": "P-001",
        "location": "Loc A",
        "google_drive_folder": None,
    }
    resp_create = await async_client.post("/projects", json=payload)
    assert resp_create.status_code == status.HTTP_201_CREATED
    created = resp_create.json()
    assert created["code"] == "P-001"
    pid = created["id"]

    # List
    resp_list = await async_client.get("/projects")
    assert resp_list.status_code == status.HTTP_200_OK
    assert any(p["id"] == pid for p in resp_list.json())

    # Duplicate create -> 409
    resp_dup = await async_client.post("/projects", json=payload)
    assert resp_dup.status_code == status.HTTP_409_CONFLICT

    # Update
    upd = {"code": "P-001", "location": "Loc B", "google_drive_folder": "folder"}
    resp_upd = await async_client.put(f"/projects/{pid}", json=upd)
    assert resp_upd.status_code == status.HTTP_200_OK
    assert resp_upd.json()["location"] == "Loc B"
    assert resp_upd.json()["google_drive_folder"] == "folder"

    # Update missing -> 404
    resp_upd_404 = await async_client.put("/projects/999999", json=upd)
    assert resp_upd_404.status_code == status.HTTP_404_NOT_FOUND

    # Delete
    resp_del = await async_client.delete(f"/projects/{pid}")
    assert resp_del.status_code == status.HTTP_204_NO_CONTENT

    # Delete missing -> 404
    resp_del_404 = await async_client.delete(f"/projects/{pid}")
    assert resp_del_404.status_code == status.HTTP_404_NOT_FOUND

    # Cleanup override
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_delete_requires_admin(async_client):
    # Arrange

    # Act: attempt delete without bearer/admin
    resp = await async_client.delete("/projects/1")

    # Assert
    assert (
        resp.status_code == status.HTTP_401_UNAUTHORIZED
        or resp.status_code == status.HTTP_403_FORBIDDEN
    )
