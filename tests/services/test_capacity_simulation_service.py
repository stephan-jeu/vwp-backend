from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.schemas.capacity import CapacitySimulationResponse, FamilyDaypartCapacity
from app.services.capacity_simulation_service import (
    _get_required_user_flag,
    _week_id,
    simulate_capacity_horizon,
    simulate_week_capacity,
)


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def scalars(self) -> Any:
        rows = self.rows

        class S:
            def unique(self) -> "S":
                # No-op for fake list
                return self

            def all(self) -> list[Any]:
                return rows

        return S()


class _FakeDB:
    def __init__(self, *, availability_rows: list[Any], users: list[Any]) -> None:
        self._availability_rows = availability_rows
        self._users = users

    async def execute(self, _stmt):  # type: ignore[no-untyped-def]
        return _FakeResult(self._availability_rows)

    async def commit(self) -> None:
        return None


@pytest.fixture()
def week_monday() -> date:
    return date(2025, 6, 2)  # Monday


def _make_visit(vid: int, fam_name: str, part: str, required: int = 1) -> Any:
    family = SimpleNamespace(name=fam_name)
    species = [SimpleNamespace(family=family, name=fam_name)]
    # Mock function name to be standard to avoid SMP trigger unless specified
    func = SimpleNamespace(name="Inventarisatie")
    return SimpleNamespace(
        id=vid,
        species=species,
        functions=[func],
        part_of_day=part,
        required_researchers=required,
    )


def _make_user(uid: int, qualifies: bool = True) -> Any:
    # The simulation uses _qualifies_user_for_visit from visit_planning_selection,
    # which we do not exercise directly here. Instead, tests that need more
    # nuanced qualification behavior should be added in that module. For the
    # capacity simulation we only care that some users exist and can consume
    # capacity buckets.
    return SimpleNamespace(id=uid, qualifies=qualifies)


# Basic helpers ---------------------------------------------------------------


def test_week_id_formats_iso_week_correctly(week_monday: date) -> None:
    assert _week_id(week_monday) == "2025-W23"


def test_get_required_user_flag_standard() -> None:
    # Updated to test the new grouping logic helper
    fam = SimpleNamespace(name="Vleermuis")
    sp = SimpleNamespace(family=fam, name="Vleermuis")
    func = SimpleNamespace(name="Inventarisatie")
    visit = SimpleNamespace(species=[sp], functions=[func])

    assert _get_required_user_flag(visit) == "Vleermuis"


# Week-level simulation -------------------------------------------------------


@pytest.mark.asyncio
async def test_simulate_week_capacity_empty_when_no_selected(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
) -> None:
    async def fake_core(_db: Any, _week_monday: date, **kwargs):
        from app.services.visit_selection_ortools import VisitSelectionResult

        return VisitSelectionResult(
            [], [], {"Ochtend": 0, "Dag": 0, "Avond": 0, "Flex": 0}
        )

    monkeypatch.setattr(
        "app.services.capacity_simulation_service.select_visits_cp_sat",
        fake_core,
    )

    fake_db = _FakeDB(availability_rows=[], users=[])

    result = await simulate_week_capacity(fake_db, week_monday)  # type: ignore[arg-type]

    assert result == {}


@pytest.mark.asyncio
async def test_simulate_week_capacity_aggregates_required_and_assigned(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
) -> None:
    # Two visits in same family/daypart, each needing one researcher.
    v1 = _make_visit(1, "Vleermuis", "Ochtend", required=1)
    v2 = _make_visit(2, "Vleermuis", "Ochtend", required=1)

    async def fake_core(_db: Any, _week_monday: date, **kwargs):
        from app.services.visit_selection_ortools import VisitSelectionResult

        return VisitSelectionResult(
            [v1, v2], [], {"Ochtend": 2, "Dag": 0, "Avond": 0, "Flex": 0}
        )

    # One user with two morning slots.
    availability_rows = [
        SimpleNamespace(
            user_id=1,
            morning_days=2,
            daytime_days=0,
            nighttime_days=0,
            flex_days=0,
        )
    ]
    fake_db = _FakeDB(availability_rows=availability_rows, users=[_make_user(1)])

    async def fake_load_users(_db: Any):  # type: ignore[no-untyped-def]
        return fake_db._users

    monkeypatch.setattr(
        "app.services.capacity_simulation_service.select_visits_cp_sat",
        fake_core,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_all_users",
        fake_load_users,
    )

    result = await simulate_week_capacity(fake_db, week_monday)  # type: ignore[arg-type]

    # Expected key is now "Vleermuis" (Capitalized by new logic)
    cell = result["Vleermuis"]["Ochtend"]
    assert isinstance(cell, FamilyDaypartCapacity)
    assert cell.required == 2
    assert cell.assigned == 2
    assert cell.shortfall == 0


@pytest.mark.asyncio
async def test_simulate_week_capacity_tracks_shortfall_when_insufficient_capacity(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
) -> None:
    # One visit requiring two researchers in the same family/daypart.
    v = _make_visit(1, "Vleermuis", "Ochtend", required=2)

    async def fake_core(_db: Any, _week_monday: date, **kwargs):
        from app.services.visit_selection_ortools import VisitSelectionResult

        return VisitSelectionResult(
            [], [v], {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0}
        )

    # One user with only one morning slot available.
    availability_rows = [
        SimpleNamespace(
            user_id=1,
            morning_days=1,
            daytime_days=0,
            nighttime_days=0,
            flex_days=0,
        )
    ]
    fake_db = _FakeDB(availability_rows=availability_rows, users=[_make_user(1)])

    async def fake_load_users(_db: Any):  # type: ignore[no-untyped-def]
        return fake_db._users

    monkeypatch.setattr(
        "app.services.capacity_simulation_service.select_visits_cp_sat",
        fake_core,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_all_users",
        fake_load_users,
    )

    result = await simulate_week_capacity(fake_db, week_monday)  # type: ignore[arg-type]

    cell = result["Vleermuis"]["Ochtend"]
    assert cell.required == 2
    assert cell.assigned == 0
    assert cell.shortfall == 2


@pytest.mark.asyncio
async def test_simulate_week_capacity_uses_flex_when_part_capacity_empty(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
) -> None:
    # One visit requiring one researcher in the morning.
    v = _make_visit(1, "Vleermuis", "Ochtend", required=1)

    async def fake_core(_db: Any, _week_monday: date, **kwargs):
        from app.services.visit_selection_ortools import VisitSelectionResult

        return VisitSelectionResult(
            [v], [], {"Ochtend": 0, "Dag": 0, "Avond": 0, "Flex": 1}
        )

    availability_rows = [
        SimpleNamespace(
            user_id=1,
            morning_days=0,
            daytime_days=0,
            nighttime_days=0,
            flex_days=1,
        )
    ]
    fake_db = _FakeDB(availability_rows=availability_rows, users=[_make_user(1)])

    async def fake_load_users(_db: Any):  # type: ignore[no-untyped-def]
        return fake_db._users

    monkeypatch.setattr(
        "app.services.capacity_simulation_service.select_visits_cp_sat",
        fake_core,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_all_users",
        fake_load_users,
    )

    result = await simulate_week_capacity(fake_db, week_monday)  # type: ignore[arg-type]

    cell = result["Vleermuis"]["Ochtend"]
    assert cell.required == 1
    assert cell.assigned == 1
    assert cell.shortfall == 0


@pytest.mark.asyncio
async def test_simulate_week_capacity_shares_user_capacity_across_families(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
) -> None:
    # Two visits in different families, same daypart. Only enough capacity
    # for one slot, so one family will show a shortfall.
    v1 = _make_visit(1, "Vleermuis", "Ochtend", required=1)
    v2 = _make_visit(2, "Zwaluw", "Ochtend", required=1)

    async def fake_core(_db: Any, _week_monday: date, **kwargs):
        # Order is important: whichever comes first will consume the slot.
        from app.services.visit_selection_ortools import VisitSelectionResult

        return VisitSelectionResult(
            [v1, v2], [], {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0}
        )

    availability_rows = [
        SimpleNamespace(
            user_id=1,
            morning_days=1,
            daytime_days=0,
            nighttime_days=0,
            flex_days=0,
        )
    ]
    fake_db = _FakeDB(availability_rows=availability_rows, users=[_make_user(1)])

    async def fake_load_users(_db: Any):  # type: ignore[no-untyped-def]
        return fake_db._users

    monkeypatch.setattr(
        "app.services.capacity_simulation_service.select_visits_cp_sat",
        fake_core,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_all_users",
        fake_load_users,
    )

    result = await simulate_week_capacity(fake_db, week_monday)  # type: ignore[arg-type]

    cell_v = result["Vleermuis"]["Ochtend"]
    cell_z = result["Zwaluw"]["Ochtend"]

    assert cell_v.required == 1
    assert cell_v.assigned == 1
    assert cell_v.shortfall == 0

    assert cell_z.required == 1
    assert cell_z.assigned + cell_z.shortfall == 1
    assert cell_z.assigned in (0, 1)


# Horizon-level simulation ----------------------------------------------------


@pytest.mark.asyncio
async def test_simulate_capacity_horizon_normalizes_start_to_monday(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # We only care that the first key corresponds to the ISO week of the
    # provided date and that the start is normalized to Monday.
    async def fake_week(db: Any, week_monday: date):  # type: ignore[no-untyped-def]
        fam = "Vleermuis"
        part = "Ochtend"
        return {
            fam: {
                part: FamilyDaypartCapacity(required=1, assigned=1, shortfall=0),
            }
        }

    monkeypatch.setattr(
        "app.services.capacity_simulation_service.simulate_week_capacity",
        fake_week,
    )

    fake_db = _FakeDB(availability_rows=[], users=[])

    # Pick a Wednesday; implementation should roll back to Monday of that week.
    some_day = date(2025, 6, 4)
    response: CapacitySimulationResponse = await simulate_capacity_horizon(
        fake_db,
        some_day,  # type: ignore[arg-type]
    )

    assert isinstance(response, CapacitySimulationResponse)
    # horizon_start must be Monday of that ISO week
    assert response.horizon_start.weekday() == 0
    iso_year, iso_week, _ = some_day.isocalendar()
    assert _week_id(response.horizon_start).startswith(f"{iso_year}-W{iso_week:02d}")
    # There should be at least one week entry
    assert response.grid
