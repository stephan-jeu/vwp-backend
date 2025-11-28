import pytest
from datetime import datetime

from app.services.soft_delete import soft_delete_entity
from app.models.project import Project
from app.models.user import User


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self):
        self.executed = []  # list of (sql_text, params)
        # Pre-wire graph ids for recursion
        self._clusters_by_project = {1: [10]}
        self._visits_by_cluster = {10: [100, 101]}
        self._aw_by_user = {5: [500]}

    async def execute(self, stmt):
        sql = str(stmt)
        self.executed.append((sql, getattr(stmt, "compile", lambda: None)))
        # Respond to SELECT of child ids to enable recursion
        if "FROM clusters" in sql and "SELECT" in sql:
            return _FakeResult(
                [
                    (cid,)
                    for pid, cids in self._clusters_by_project.items()
                    for cid in cids
                ]
            )
        if "FROM visits" in sql and "SELECT" in sql:
            return _FakeResult(
                [
                    (vid,)
                    for cid, vids in self._visits_by_cluster.items()
                    for vid in vids
                ]
            )
        if "FROM availability_weeks" in sql and "SELECT" in sql:
            return _FakeResult(
                [(awid,) for uid, awids in self._aw_by_user.items() for awid in awids]
            )
        return _FakeResult([])


@pytest.mark.asyncio
async def test_soft_delete_project_cascades_to_clusters_and_visits():
    # Arrange
    db = _FakeSession()
    proj = Project(id=1, code="P", location="L")

    # Act
    await soft_delete_entity(db, proj, cascade=True)

    # Assert
    assert proj.deleted_at is not None and isinstance(proj.deleted_at, datetime)
    sql_texts = "\n".join(sql for sql, _ in db.executed)
    # One UPDATE on clusters and one UPDATE on visits
    assert "UPDATE clusters" in sql_texts
    assert "UPDATE visits" in sql_texts


@pytest.mark.asyncio
async def test_soft_delete_user_cascades_to_availability():
    # Arrange
    db = _FakeSession()
    user = User(id=5, email="u@example.com")

    # Act
    await soft_delete_entity(db, user, cascade=True)

    # Assert
    assert user.deleted_at is not None
    sql_texts = "\n".join(sql for sql, _ in db.executed)
    assert "UPDATE availability_weeks" in sql_texts
