import pytest
from datetime import date
from fastapi import status
from unittest.mock import MagicMock

from app.models.visit import Visit
from app.models.cluster import Cluster
from app.models.project import Project
from app.models.function import Function
from app.models.species import Species
from app.services.visit_status_service import VisitStatusCode
from db.session import get_db

class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        class _Scalars:
            def __init__(self, rows):
                self._rows = list(rows)

            def all(self):
                return list(self._rows)
            
            def first(self):
                return self._rows[0] if self._rows else None

        return _Scalars(self._rows)

class _FakeSession:
    def __init__(self, visits):
        self._visits = visits
        self._call_count = 0

    async def execute(self, stmt):
        self._call_count += 1
        if self._call_count == 1:
            # First call: Select IDs
            # returns scalars().all() -> [1, 2, ...]
            ids = [v.id for v in self._visits]
            return _FakeResult(ids)
        else:
            # Second call: Loading visits
            return _FakeResult(self._visits)

@pytest.mark.asyncio
async def test_export_visits_csv(async_client, app, mocker):
    # Arrange
    from app.services.security import get_current_user
    
    # Mock user
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.admin = True
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Mock DB
    p = Project(id=1, code="P-123", location="Locality")
    c = Cluster(id=1, project_id=1, cluster_number="C1", address="Address 1")
    c.project = p
    
    f = Function(id=1, name="MyFunc")
    s = Species(id=1, name="MySpecies", abbreviation="MS")
    
    v1 = Visit(
        id=1, 
        cluster_id=1, 
        visit_nr=1, 
        planned_date=date(2025, 1, 1),
        functions=[f],
        species=[s],
        researchers=[],
        deleted_at=None
    )
    v1.cluster = c
    
    visits = [v1]
    fake_db = _FakeSession(visits)
    app.dependency_overrides[get_db] = lambda: fake_db

    # Mock resolve_visit_statuses
    mocker.patch(
        "app.routers.visits.resolve_visit_statuses",
        return_value={1: VisitStatusCode.PLANNED}
    )

    # Act
    resp = await async_client.get("/visits/export")

    # Assert
    assert resp.status_code == status.HTTP_200_OK
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    content = resp.text
    
    # Verify CSV content
    lines = content.strip().split("\n")
    assert len(lines) >= 2 # Header + 1 row
    
    # Validate header
    assert "Projectcode" in lines[0]
    assert "Status" in lines[0]
    
    # Validate row
    row = lines[1].split(",")
    # Check project code
    assert "P-123" in lines[1]
    # Check status
    assert "planned" in lines[1]
    # Check date
    assert "01-01-2025" in lines[1]
    # Check function
    assert "MyFunc" in lines[1]

    # Cleanup
    app.dependency_overrides.clear()
