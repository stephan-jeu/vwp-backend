import pytest
from fastapi import status
from uuid import uuid4

from app.models.project import Project
from db.session import get_db
from sqlalchemy.exc import IntegrityError


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        class _Scalars:
            def __init__(self, rows):
                self._rows = list(rows)

            def all(self):
                return list(self._rows)

        return _Scalars(self._rows)


class _FakeSession:
    def __init__(self):
        self._projects: dict[int, Project] = {}
        self._pending: list[Project] = []
        self._next_id: int = 1

    async def execute(self, _stmt):  # type: ignore[no-untyped-def]
        # list_projects orders by code; we mimic deterministic ordering here
        rows = sorted(self._projects.values(), key=lambda p: p.code)
        return _FakeResult(rows)

    def add(self, obj: Project) -> None:
        self._pending.append(obj)

    async def commit(self) -> None:
        # Apply pending changes and enforce unique project code
        for obj in list(self._pending):
            if isinstance(obj, Project):
                for existing in self._projects.values():
                    if existing.code == obj.code and existing.id != getattr(
                        obj, "id", None
                    ):
                        self._pending.clear()
                        raise IntegrityError("duplicate code", params=None, orig=None)
                if getattr(obj, "id", None) is None:
                    obj.id = self._next_id
                    self._next_id += 1
                self._projects[obj.id] = obj
        self._pending.clear()

    async def rollback(self) -> None:
        self._pending.clear()

    async def refresh(self, _obj: Project) -> None:
        # Objects are already live Python instances; nothing to do.
        return None

    async def get(self, model, obj_id: int):  # type: ignore[no-untyped-def]
        if model is Project:
            proj = self._projects.get(obj_id)
            if proj is not None and getattr(proj, "deleted_at", None) is None:
                return proj
        return None


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

    class _FakeAdmin:
        id = 1

    app.dependency_overrides[require_admin] = lambda: _FakeAdmin()

    # Override DB dependency with in-memory fake session
    fake_db = _FakeSession()

    async def _override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_get_db

    # Mock out side-effecting services
    mocker.patch("app.routers.projects.log_activity", return_value=None)

    async def _fake_soft_delete(_db, instance, cascade: bool = True):  # type: ignore[unused-argument]
        # Mark as soft-deleted so subsequent lookups behave like production
        setattr(instance, "deleted_at", 1)

    mocker.patch("app.routers.projects.soft_delete_entity", _fake_soft_delete)

    # Use a unique code per test run to avoid conflicts within the fake session
    code = f"P-{uuid4()}"

    # Create
    payload = {
        "code": code,
        "location": "Loc A",
        "google_drive_folder": None,
        "quote": False,
    }
    resp_create = await async_client.post("/projects", json=payload)
    assert resp_create.status_code == status.HTTP_201_CREATED
    created = resp_create.json()
    assert created["code"] == code
    assert created["quote"] is False
    pid = created["id"]

    # List
    resp_list = await async_client.get("/projects")
    assert resp_list.status_code == status.HTTP_200_OK
    assert any(p["id"] == pid for p in resp_list.json())

    # Duplicate create -> 409
    resp_dup = await async_client.post("/projects", json=payload)
    assert resp_dup.status_code == status.HTTP_409_CONFLICT

    # Update
    upd = {
        "code": code,
        "location": "Loc B",
        "google_drive_folder": "folder",
        "quote": True,
    }
    resp_upd = await async_client.put(f"/projects/{pid}", json=upd)
    assert resp_upd.status_code == status.HTTP_200_OK
    assert resp_upd.json()["location"] == "Loc B"
    body = resp_upd.json()
    assert body["google_drive_folder"] == "folder"
    assert body["quote"] is True

    # Update missing -> 404
    resp_upd_404 = await async_client.put("/projects/999999", json=upd)
    assert resp_upd_404.status_code == status.HTTP_404_NOT_FOUND

    # Delete
    resp_del = await async_client.delete(f"/projects/{pid}")
    assert resp_del.status_code == status.HTTP_204_NO_CONTENT

    # Delete missing -> 404
    resp_del_404 = await async_client.delete(f"/projects/{pid}")
    assert resp_del_404.status_code == status.HTTP_404_NOT_FOUND

    # Cleanup overrides
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
