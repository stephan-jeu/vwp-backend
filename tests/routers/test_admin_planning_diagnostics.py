import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import app.routers.admin as admin_module
from app.routers.admin import get_planning_diagnostics
from app.models.visit import Visit
from app.models.cluster import Cluster
from app.models.project import Project


def _result(rows):
    res = MagicMock()
    res.scalars.return_value.all.return_value = rows
    res.scalars.return_value.unique.return_value.all.return_value = rows
    return res


def _make_visit(**kwargs) -> Visit:
    project = Project(id=1, code="P-1", location="Loc")
    cluster = Cluster(id=1, project_id=1, cluster_number="C1", address="Addr")
    cluster.project = project

    visit = Visit(id=42, cluster_id=1, visit_nr=2, deleted_at=None, **kwargs)
    visit.cluster = cluster
    return visit


@pytest.mark.asyncio
async def test_planned_week_out_of_window_is_flagged(monkeypatch):
    monkeypatch.setattr(admin_module._settings, "feature_daily_planning", False)

    year = date.today().year
    week_monday = date.fromisocalendar(year, 10, 1)
    # from_date shifted well past the already-assigned week, e.g. after
    # visit_execution_updates pushed it out for a related visit's execution.
    visit = _make_visit(
        planned_week=10,
        from_date=week_monday + timedelta(days=20),
        to_date=week_monday + timedelta(days=50),
    )

    db = AsyncMock()
    db.execute.side_effect = [
        _result([]),  # log_stmt: no ActivityLog diagnostics
        _result([]),  # invalid_stmt: no inverted from/to windows
        _result([visit]),  # planned_stmt: our conflicting visit
    ]

    diagnostics = await get_planning_diagnostics(None, db)

    assert len(diagnostics) == 1
    d = diagnostics[0]
    assert d.visit_id == 42
    assert d.reason_code == "planned_week_buiten_venster"
    assert "week 10" in d.reason_nl


@pytest.mark.asyncio
async def test_planned_week_inside_window_is_not_flagged(monkeypatch):
    monkeypatch.setattr(admin_module._settings, "feature_daily_planning", False)

    year = date.today().year
    week_monday = date.fromisocalendar(year, 10, 1)
    visit = _make_visit(
        planned_week=10,
        from_date=week_monday,
        to_date=week_monday + timedelta(days=30),
    )

    db = AsyncMock()
    db.execute.side_effect = [
        _result([]),
        _result([]),
        _result([visit]),
    ]

    diagnostics = await get_planning_diagnostics(None, db)

    assert diagnostics == []


@pytest.mark.asyncio
async def test_planned_date_out_of_window_is_flagged_in_daily_mode(monkeypatch):
    monkeypatch.setattr(admin_module._settings, "feature_daily_planning", True)

    visit = _make_visit(
        planned_date=date(2025, 1, 1),
        from_date=date(2025, 1, 20),
        to_date=date(2025, 2, 1),
    )

    db = AsyncMock()
    db.execute.side_effect = [
        _result([]),
        _result([]),
        _result([visit]),
    ]

    diagnostics = await get_planning_diagnostics(None, db)

    assert len(diagnostics) == 1
    assert diagnostics[0].reason_code == "planned_week_buiten_venster"
    assert "geplande datum" in diagnostics[0].reason_nl
