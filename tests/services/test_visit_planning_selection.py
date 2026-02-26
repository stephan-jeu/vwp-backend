from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession
from app.services.visit_planning_selection import select_visits_for_week, _apply_existing_assignments_to_capacities


# ---- Test helpers -------------------------------------------------------------


def make_function(name: str) -> Any:
    return SimpleNamespace(name=name)


def make_family(priority: int) -> Any:
    return SimpleNamespace(priority=priority)


def make_species(name: str, family_priority: int) -> Any:
    return SimpleNamespace(name=name, family=make_family(family_priority))


def make_visit(
    *,
    vid: int,
    part_of_day: str | None,
    from_date: date,
    to_date: date,
    required_researchers: int | None = None,
    priority: bool = False,
    hub: bool = False,
    fiets: bool = False,
    dvp: bool = False,
    wbc: bool = False,
    sleutel: bool = False,
    function_names: list[str] | None = None,
    species_defs: list[tuple[str, int]] | None = None,  # (name, family_priority)
) -> Any:
    functions = [make_function(n) for n in (function_names or [])]
    species = [make_species(n, fp) for (n, fp) in (species_defs or [])]
    return SimpleNamespace(
        id=vid,
        part_of_day=part_of_day,
        from_date=from_date,
        to_date=to_date,
        required_researchers=required_researchers,
        priority=priority,
        hub=hub,
        fiets=fiets,
        dvp=dvp,
        wbc=wbc,
        sleutel=sleutel,
        functions=functions,
        species=species,
        provisional_week=None,
        provisional_locked=False,
    )


@pytest.fixture()
def week_monday() -> date:
    # Pick a stable week
    return date(2025, 6, 2)  # Monday


# ---- Tests -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_respects_capacity_and_priority_order_async(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 3, "Dag": 0, "Avond": 0, "Flex": 1}

    v1 = make_visit(
        vid=1,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=4),
        required_researchers=1,
        priority=True,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v2 = make_visit(
        vid=2,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=10),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v3 = make_visit(
        vid=3,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=20),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("B", 3)],
    )
    v4 = make_visit(
        vid=4,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=20),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("C", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v4, v3, v2, v1]

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    result = await select_visits_for_week(db=None, week_monday=week_monday)  # type: ignore[arg-type]

    # Assert: all four selected thanks to 3 dedicated + 1 flex
    assert result["selected_visit_ids"] == [1, 2, 3, 4]
    assert result["skipped_visit_ids"] == []
    # Remaining caps: Ochtend=0, Flex=0
    assert result["capacity_remaining"]["Ochtend"] == 0
    assert result["capacity_remaining"]["Flex"] == 0


@pytest.mark.asyncio
async def test_unknown_part_of_day_is_skipped(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 2, "Dag": 0, "Avond": 0, "Flex": 0}

    v_ok = make_visit(
        vid=1,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=2),
        required_researchers=1,
        function_names=["SMP X"],
        species_defs=[("A", 5)],
    )
    v_bad = make_visit(
        vid=2,
        part_of_day=None,
        from_date=week_monday,
        to_date=week_monday + timedelta(days=2),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v_bad, v_ok]

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    result = await select_visits_for_week(db=None, week_monday=week_monday)  # type: ignore[arg-type]

    assert result["selected_visit_ids"] == [1]
    assert result["skipped_visit_ids"] == [2]


@pytest.mark.asyncio
async def test_required_researchers_consumes_capacity_and_flex(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        # Ochtend capacity = 2, flex = 1
        return {"Ochtend": 2, "Dag": 0, "Avond": 0, "Flex": 1}

    v_need3 = make_visit(
        vid=10,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=4),
        required_researchers=3,
        function_names=["X"],
        species_defs=[("A", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v_need3]

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    result = await select_visits_for_week(db=None, week_monday=week_monday)  # type: ignore[arg-type]

    # 2 dedicated + 1 flex -> should fit
    assert result["selected_visit_ids"] == [10]
    assert result["capacity_remaining"]["Ochtend"] == 0
    assert result["capacity_remaining"]["Flex"] == 0


@pytest.mark.asyncio
async def test_spare_capacity_is_applied(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    # We simulate AvailabilityWeek sum via fake _load_week_capacity directly pre-spared
    # Here we ensure behavior by forcing caps to reflect post-spare numbers
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0}

    v1 = make_visit(
        vid=21,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=4),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v2 = make_visit(
        vid=22,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=4),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v1, v2]

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    result = await select_visits_for_week(db=None, week_monday=week_monday)  # type: ignore[arg-type]

    assert result["selected_visit_ids"] == [21]
    assert result["skipped_visit_ids"] == [22]


@pytest.mark.asyncio
async def test_priority_tiers_global_order(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        # plenty of capacity so all are selected
        return {"Ochtend": 10, "Dag": 0, "Avond": 0, "Flex": 0}

    # Same base window except the deadline case
    base_from = week_monday
    base_to = week_monday + timedelta(days=20)

    v_prio = make_visit(
        vid=1,
        part_of_day="Ochtend",
        from_date=base_from,
        to_date=base_to,
        required_researchers=1,
        priority=True,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_dead = make_visit(
        vid=2,
        part_of_day="Ochtend",
        from_date=base_from,
        to_date=week_monday + timedelta(days=10),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_fam3 = make_visit(
        vid=3,
        part_of_day="Ochtend",
        from_date=base_from,
        to_date=base_to,
        required_researchers=1,
        function_names=["X"],
        species_defs=[("B", 3)],
    )
    v_smp = make_visit(
        vid=4,
        part_of_day="Ochtend",
        from_date=base_from,
        to_date=base_to,
        required_researchers=1,
        function_names=["SMP Groep"],
        species_defs=[("A", 5)],
    )
    v_route = make_visit(
        vid=5,
        part_of_day="Ochtend",
        from_date=base_from,
        to_date=base_to,
        required_researchers=1,
        function_names=["Vliegroute inspectie"],
        species_defs=[("A", 5)],
    )
    v_hub = make_visit(
        vid=6,
        part_of_day="Ochtend",
        from_date=base_from,
        to_date=base_to,
        required_researchers=1,
        hub=True,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_sleut = make_visit(
        vid=7,
        part_of_day="Ochtend",
        from_date=base_from,
        to_date=base_to,
        required_researchers=1,
        sleutel=True,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_misc = make_visit(
        vid=8,
        part_of_day="Ochtend",
        from_date=base_from,
        to_date=base_to,
        required_researchers=1,
        fiets=True,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_none = make_visit(
        vid=9,
        part_of_day="Ochtend",
        from_date=base_from,
        to_date=base_to,
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        # Deliberately shuffled
        return [v_none, v_misc, v_sleut, v_hub, v_route, v_smp, v_fam3, v_dead, v_prio]

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    result = await select_visits_for_week(db=None, week_monday=week_monday)  # type: ignore[arg-type]

    assert result["selected_visit_ids"] == [1, 2, 3, 4, 5, 6, 7, 8, 9]


@pytest.mark.asyncio
async def test_tie_breakers_by_dates_then_id(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 10, "Dag": 0, "Avond": 0, "Flex": 0}

    # All no-tiers so weight=0; ordering by to_date, then from_date, then id
    v_late = make_visit(
        vid=30,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=30),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_early = make_visit(
        vid=31,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=5),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_same_to_from_earlier = make_visit(
        vid=32,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=10),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_same_to_from_later = make_visit(
        vid=33,
        part_of_day="Ochtend",
        from_date=week_monday + timedelta(days=1),
        to_date=week_monday + timedelta(days=10),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_same_dates_lower_id = make_visit(
        vid=10,
        part_of_day="Ochtend",
        from_date=week_monday + timedelta(days=2),
        to_date=week_monday + timedelta(days=15),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_same_dates_higher_id = make_visit(
        vid=99,
        part_of_day="Ochtend",
        from_date=week_monday + timedelta(days=2),
        to_date=week_monday + timedelta(days=15),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [
            v_late,
            v_same_to_from_later,
            v_same_dates_higher_id,
            v_same_to_from_earlier,
            v_same_dates_lower_id,
            v_early,
        ]

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    result = await select_visits_for_week(db=None, week_monday=week_monday)  # type: ignore[arg-type]

    # Expected order: by earliest to_date -> earliest from_date -> lowest id
    assert result["selected_visit_ids"] == [31, 32, 33, 10, 99, 30]


@pytest.mark.asyncio
async def test_capacity_insufficient_selects_highest_weight(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 2, "Dag": 0, "Avond": 0, "Flex": 0}

    v_high = make_visit(
        vid=1,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=20),
        required_researchers=1,
        priority=True,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_mid = make_visit(
        vid=2,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=20),
        required_researchers=1,
        function_names=["SMP Z"],
        species_defs=[("A", 5)],
    )
    v_low = make_visit(
        vid=3,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=20),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v_low, v_mid, v_high]

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    result = await select_visits_for_week(db=None, week_monday=week_monday)  # type: ignore[arg-type]

    assert result["selected_visit_ids"] == [1, 2]
    assert result["skipped_visit_ids"] == [3]


@pytest.mark.asyncio
async def test_sleutel_between_hub_and_misc(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 3, "Dag": 0, "Avond": 0, "Flex": 0}

    v_hub = make_visit(
        vid=1,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=20),
        required_researchers=1,
        hub=True,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_sleut = make_visit(
        vid=2,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=20),
        required_researchers=1,
        sleutel=True,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_misc = make_visit(
        vid=3,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=20),
        required_researchers=1,
        fiets=True,
        function_names=["X"],
        species_defs=[("A", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v_misc, v_sleut, v_hub]

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    result = await select_visits_for_week(db=None, week_monday=week_monday)  # type: ignore[arg-type]

    assert result["selected_visit_ids"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_flex_consumed_when_period_deficit(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        # No morning capacity, but flex can cover two
        return {"Ochtend": 0, "Dag": 0, "Avond": 0, "Flex": 2}

    v_high = make_visit(
        vid=11,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=10),
        required_researchers=1,
        priority=True,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_mid = make_visit(
        vid=12,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=10),
        required_researchers=1,
        function_names=["SMP Alpha"],
        species_defs=[("A", 5)],
    )
    v_low = make_visit(
        vid=13,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=10),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        # unordered to ensure sorting
        return [v_low, v_mid, v_high]

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    result = await select_visits_for_week(db=None, week_monday=week_monday)  # type: ignore[arg-type]

    # Expect top two selected using flex, lowest skipped
    assert result["selected_visit_ids"] == [11, 12]
    assert result["skipped_visit_ids"] == [13]


@pytest.mark.asyncio
async def test_required_researchers_consumes_multiple_slots(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        # Two morning slots available, no flex
        return {"Ochtend": 2, "Dag": 0, "Avond": 0, "Flex": 0}

    v_big = make_visit(
        vid=20,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=7),
        required_researchers=2,
        priority=True,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_small = make_visit(
        vid=21,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=7),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v_small, v_big]

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    result = await select_visits_for_week(db=None, week_monday=week_monday)  # type: ignore[arg-type]

    # v_big takes both slots; v_small cannot fit afterwards
    assert result["selected_visit_ids"] == [20]
    assert result["skipped_visit_ids"] == [21]


@pytest.mark.asyncio
async def test_function_name_detection_smp_and_route_case_insensitive(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 3, "Dag": 0, "Avond": 0, "Flex": 0}

    v_smp_weird = make_visit(
        vid=40,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=14),
        required_researchers=1,
        function_names=[" smp  Team"],
        species_defs=[("A", 5)],
    )
    v_route_case = make_visit(
        vid=41,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=14),
        required_researchers=1,
        function_names=["FoErAgEeRgEbIeD delta"],
        species_defs=[("A", 5)],
    )
    v_plain = make_visit(
        vid=42,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=14),
        required_researchers=1,
        function_names=["x"],
        species_defs=[("A", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v_plain, v_route_case, v_smp_weird]

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    result = await select_visits_for_week(db=None, week_monday=week_monday)  # type: ignore[arg-type]

    # Expected order: SMP-like first, then route-like, then plain
    assert result["selected_visit_ids"] == [40, 41, 42]


@pytest.mark.asyncio
async def test_flex_shared_across_parts_not_overdrawn(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        # No dedicated capacity, only 1 flex for the whole week
        return {"Ochtend": 0, "Dag": 0, "Avond": 0, "Flex": 1}

    v_high_morning = make_visit(
        vid=50,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=7),
        required_researchers=1,
        priority=True,
        function_names=["X"],
        species_defs=[("A", 5)],
    )
    v_mid_evening = make_visit(
        vid=51,
        part_of_day="Avond",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=7),
        required_researchers=1,
        function_names=["SMP Z"],
        species_defs=[("A", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        # lower-priority comes first to ensure sorting handles it
        return [v_mid_evening, v_high_morning]

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    result = await select_visits_for_week(db=None, week_monday=week_monday)  # type: ignore[arg-type]

    # Only the highest-priority one should use the single flex day
    assert result["selected_visit_ids"] == [50]
    assert result["skipped_visit_ids"] == [51]


@pytest.mark.asyncio
async def test_load_week_capacity_applies_spare_subtraction():
    from app.services.visit_planning_selection import _load_week_capacity
    from types import SimpleNamespace
    from unittest.mock import patch

    # Create fake rows with totals: morning=3, day=3, night=3, flex=2
    rows = [
        SimpleNamespace(morning_days=2, daytime_days=1, nighttime_days=1, flex_days=1, user_id=1),
        SimpleNamespace(morning_days=1, daytime_days=2, nighttime_days=2, flex_days=1, user_id=2),
    ]

    class FakeResult:
        def scalars(self):
            class S:
                def all(self_non):
                    return rows

            return S()

    async def fake_execute(_stmt):
        return FakeResult()

    fake_db = SimpleNamespace(execute=fake_execute)

    with patch("core.settings.get_settings") as mock_get_settings:
        mock_get_settings.return_value.feature_strict_availability = False
        caps = await _load_week_capacity(fake_db, week=1)

    # Spare subtraction configured in service: Ochtend-1, Dag-2, Avond-2
    # So: morning 3-1=2, day 3-2=1, night 3-2=1, flex unchanged=2
    assert caps == {"Ochtend": 2, "Dag": 1, "Avond": 1, "Flex": 2}


# -----------------
# Researcher assignment tests
# -----------------


def make_user(
    uid: int,
    full_name: str = "U",
    **flags: bool,
):
    from types import SimpleNamespace

    defaults = {
        "smp_huismus": False,
        "smp_vleermuis": False,
        "smp_gierzwaluw": False,
        "vrfg": False,
        "hub": False,
        "fiets": False,
        "wbc": False,
        "dvp": False,
        "sleutel": False,
        "pad": False,
        "langoor": False,
        "roofvogel": False,
        "vleermuis": False,
        "zwaluw": False,
        "vlinder": False,
        "teunisbloempijlstaart": False,
        "zangvogel": False,
        "biggenkruid": False,
        "schijfhoren": False,
    }
    defaults.update(flags)
    return SimpleNamespace(id=uid, full_name=full_name, **defaults)


async def _fake_db_with_users(users: list[Any]):
    class FakeResult:
        def scalars(self):
            class S:
                def all(self_non):
                    return users

            return S()

    async def execute(_stmt):
        return FakeResult()

    async def commit():
        return None

    from types import SimpleNamespace

    return SimpleNamespace(execute=execute, commit=commit)


@pytest.mark.asyncio
async def test_assign_requires_all_families(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 5, "Dag": 0, "Avond": 0, "Flex": 0}

    # Visit requires Vleermuis AND Pad
    v = make_visit(
        vid=101,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=7),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("Vleermuis", 5), ("Pad", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v]

    u1 = make_user(1, "A", vleermuis=True, pad=False)
    u2 = make_user(2, "B", vleermuis=True, pad=True)
    fake_db = await _fake_db_with_users([u1, u2])

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    async def fake_user_daypart_caps_fn(_db: Any, _week: int):
        return {
            uid: {"Ochtend": 10, "Dag": 10, "Avond": 10, "Flex": 10}
            for uid in [1, 2, 3]
        }

    async def fake_user_caps_fn(_db: Any, _week: int):
        return {uid: 10 for uid in [1, 2, 3]}

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_user_daypart_caps_fn,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities", fake_user_caps_fn
    )

    await select_visits_for_week(db=fake_db, week_monday=week_monday)  # type: ignore[arg-type]

    assert [u.full_name for u in getattr(v, "researchers", [])] == ["B"]


@pytest.mark.asyncio
async def test_assign_requires_smp(monkeypatch: pytest.MonkeyPatch, week_monday: date):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0}

    v = make_visit(
        vid=102,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=7),
        required_researchers=1,
        function_names=["SMP Inspectie"],
        species_defs=[("A", 5)],
    )
    # Ensure family name is present so SMP specialization can be determined (Vleermuis -> smp_vleermuis)
    v.species[0].family.name = "Vleermuis"

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v]

    # Both users qualify for the Vleermuis family; only B has the SMP specialization
    u1 = make_user(1, "A", smp_vleermuis=False)
    u2 = make_user(2, "B", smp_vleermuis=True)
    fake_db = await _fake_db_with_users([u1, u2])

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    async def fake_user_daypart_caps_fn(_db: Any, _week: int):
        return {
            uid: {"Ochtend": 10, "Dag": 10, "Avond": 10, "Flex": 10}
            for uid in [1, 2, 3]
        }

    async def fake_user_caps_fn(_db: Any, _week: int):
        return {uid: 10 for uid in [1, 2, 3]}

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_user_daypart_caps_fn,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities", fake_user_caps_fn
    )

    await select_visits_for_week(db=fake_db, week_monday=week_monday)  # type: ignore[arg-type]

    assert [u.full_name for u in getattr(v, "researchers", [])] == ["B"]


@pytest.mark.asyncio
async def test_assign_requires_vrfg(monkeypatch: pytest.MonkeyPatch, week_monday: date):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0}

    v = make_visit(
        vid=103,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=7),
        required_researchers=1,
        function_names=["Foerageergebied"],
        species_defs=[("A", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v]

    u1 = make_user(1, "A", vrfg=False)
    u2 = make_user(2, "B", vrfg=True)
    fake_db = await _fake_db_with_users([u1, u2])

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    async def fake_user_daypart_caps_fn(_db: Any, _week: int):
        return {
            uid: {"Ochtend": 10, "Dag": 10, "Avond": 10, "Flex": 10}
            for uid in [1, 2, 3]
        }

    async def fake_user_caps_fn(_db: Any, _week: int):
        return {uid: 10 for uid in [1, 2, 3]}

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_user_daypart_caps_fn,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities", fake_user_caps_fn
    )

    await select_visits_for_week(db=fake_db, week_monday=week_monday)  # type: ignore[arg-type]

    assert [u.full_name for u in getattr(v, "researchers", [])] == ["B"]


@pytest.mark.asyncio
async def test_assign_requires_visit_flags(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0}

    v = make_visit(
        vid=104,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=7),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("A", 5)],
        hub=True,
        fiets=True,
        wbc=True,
        dvp=True,
        sleutel=False,
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v]

    u1 = make_user(1, "A", hub=True, fiets=True, wbc=False, dvp=True, sleutel=True)
    u2 = make_user(2, "B", hub=True, fiets=True, wbc=True, dvp=True, sleutel=True)
    fake_db = await _fake_db_with_users([u1, u2])

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    async def fake_user_daypart_caps_fn(_db: Any, _week: int):
        return {
            uid: {"Ochtend": 10, "Dag": 10, "Avond": 10, "Flex": 10}
            for uid in [1, 2, 3]
        }

    async def fake_user_caps_fn(_db: Any, _week: int):
        return {uid: 10 for uid in [1, 2, 3]}

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_user_daypart_caps_fn,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities", fake_user_caps_fn
    )

    await select_visits_for_week(db=fake_db, week_monday=week_monday)  # type: ignore[arg-type]

    assert [u.full_name for u in getattr(v, "researchers", [])] == ["B"]


@pytest.mark.asyncio
async def test_sleutel_requires_at_least_one_intern(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    """Sleutel visits require at least one INTERN among assigned researchers.

    We create a sleutel visit requiring two researchers. Only one of the
    eligible users has contract type Intern; the other has a different
    contract. The planner must select both, but ensure the INTERN is always
    included.
    """

    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 2, "Dag": 0, "Avond": 0, "Flex": 0}

    v = make_visit(
        vid=1041,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=7),
        required_researchers=2,
        function_names=["X"],
        species_defs=[("A", 5)],
        hub=True,
        fiets=True,
        wbc=True,
        dvp=True,
        sleutel=True,
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v]

    # One non-intern and one INTERN; both satisfy visit flags, but at least one
    # INTERN must be present in the final assignment.
    u1 = make_user(
        1,
        "NonIntern",
        hub=True,
        fiets=True,
        wbc=True,
        dvp=True,
        contract="ZZP",
    )
    u2 = make_user(
        2,
        "Intern",
        hub=True,
        fiets=True,
        wbc=True,
        dvp=True,
        contract="Intern",
    )
    fake_db = await _fake_db_with_users([u1, u2])

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    async def fake_user_daypart_caps_fn(_db: Any, _week: int):
        return {
            uid: {"Ochtend": 10, "Dag": 10, "Avond": 10, "Flex": 10}
            for uid in [1, 2, 3]
        }

    async def fake_user_caps_fn(_db: Any, _week: int):
        return {uid: 10 for uid in [1, 2, 3]}

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_user_daypart_caps_fn,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities", fake_user_caps_fn
    )

    await select_visits_for_week(db=fake_db, week_monday=week_monday)  # type: ignore[arg-type]

    assigned_names = [u.full_name for u in getattr(v, "researchers", [])]
    # Both researchers should be assigned and at least one INTERN must be
    # present.
    assert sorted(assigned_names) == ["Intern", "NonIntern"]


@pytest.mark.asyncio
async def test_single_user_can_be_assigned_to_multiple_visits_when_capacity_allows(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 2, "Dag": 0, "Avond": 0, "Flex": 0}

    v1 = make_visit(
        vid=105,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=7),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("Vleermuis", 5)],
    )
    v2 = make_visit(
        vid=106,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=7),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("Vleermuis", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v1, v2]

    # Only one eligible user; with per-user capacities this user can now be
    # assigned to multiple visits in the same week as long as capacity
    # permits.
    u1 = make_user(1, "A", vleermuis=True)
    u2 = make_user(2, "B", vleermuis=False)
    fake_db = await _fake_db_with_users([u1, u2])

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    async def fake_user_daypart_caps_fn(_db: Any, _week: int):
        return {
            uid: {"Ochtend": 10, "Dag": 10, "Avond": 10, "Flex": 10}
            for uid in [1, 2, 3]
        }

    async def fake_user_caps_fn(_db: Any, _week: int):
        return {uid: 10 for uid in [1, 2, 3]}

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_user_daypart_caps_fn,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities", fake_user_caps_fn
    )

    await select_visits_for_week(db=fake_db, week_monday=week_monday)  # type: ignore[arg-type]

    counts = [len(getattr(v, "researchers", [])) for v in (v1, v2)]
    assert counts == [1, 1]


@pytest.mark.asyncio
async def test_single_user_not_assigned_more_visits_than_feasible_days(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    """A user with high weekly capacity but limited feasible days can't get too many visits.

    We construct three visits that are only executable on Thursday/Friday of the work
    week (Mon–Fri). The user has morning capacity for five days in the AvailabilityWeek
    row, but in reality there are only two feasible work days for these visits. The
    planner must therefore assign this user to at most two of the three visits.
    """

    # Global week-level capacity: pretend there are 5 morning slots available so
    # capacity alone would allow three visits.
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 5, "Dag": 0, "Avond": 0, "Flex": 0}

    # All visits only become executable from Thursday onwards within the week.
    thursday = week_monday + timedelta(days=3)
    friday = week_monday + timedelta(days=4)

    v1 = make_visit(
        vid=2010,
        part_of_day="Ochtend",
        from_date=thursday,
        to_date=friday,
        required_researchers=1,
        function_names=["X"],
        species_defs=[("Vleermuis", 5)],
    )
    v2 = make_visit(
        vid=2011,
        part_of_day="Ochtend",
        from_date=thursday,
        to_date=friday,
        required_researchers=1,
        function_names=["X"],
        species_defs=[("Vleermuis", 5)],
    )
    v3 = make_visit(
        vid=2012,
        part_of_day="Ochtend",
        from_date=thursday,
        to_date=friday,
        required_researchers=1,
        function_names=["X"],
        species_defs=[("Vleermuis", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        # Order should not matter; planner must respect per-day feasibility.
        return [v1, v2, v3]

    # One eligible user for Vleermuis visits.
    u1 = make_user(1, "A", vleermuis=True)
    fake_db = await _fake_db_with_users([u1])

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    async def fake_user_daypart_caps_fn(_db: Any, _week: int):
        return {
            uid: {"Ochtend": 10, "Dag": 10, "Avond": 10, "Flex": 10}
            for uid in [1, 2, 3]
        }

    async def fake_user_caps_fn(_db: Any, _week: int):
        return {uid: 10 for uid in [1, 2, 3]}

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_user_daypart_caps_fn,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities", fake_user_caps_fn
    )
    # This test verifies the 1-visit-per-day coordination rule (non-strict behaviour).
    from core.settings import get_settings as _real_get_settings
    _non_strict = _real_get_settings().model_copy(
        update={"feature_strict_availability": False}
    )
    monkeypatch.setattr(
        "app.services.visit_selection_ortools.get_settings", lambda: _non_strict
    )

    await select_visits_for_week(db=fake_db, week_monday=week_monday)  # type: ignore[arg-type]

    assigned_counts = [len(getattr(v, "researchers", [])) for v in (v1, v2, v3)]
    assert sum(assigned_counts) <= 2


@pytest.mark.asyncio
async def test_single_user_not_assigned_two_visits_same_day_across_dayparts(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    """A user cannot receive two visits on the same day across different parts.

    We construct two visits that are only executable on the same weekday within
    the work week (Mon–Fri), one in the morning and one in the evening. Global
    capacity would allow both visits, but the per-day safeguard must ensure at
    most one of them is assigned to the single eligible user.
    """

    async def fake_load_caps(_db: Any, _week: int) -> dict:
        # Capacity alone would allow both visits to be selected.
        return {"Ochtend": 1, "Dag": 0, "Avond": 1, "Flex": 0}

    # Both visits are restricted to Thursday of the work week.
    thursday = week_monday + timedelta(days=3)

    v_morning = make_visit(
        vid=3010,
        part_of_day="Ochtend",
        from_date=thursday,
        to_date=thursday,
        required_researchers=1,
        function_names=["X"],
        species_defs=[("Vleermuis", 5)],
    )
    v_evening = make_visit(
        vid=3011,
        part_of_day="Avond",
        from_date=thursday,
        to_date=thursday,
        required_researchers=1,
        function_names=["X"],
        species_defs=[("Vleermuis", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v_morning, v_evening]

    # One eligible user for Vleermuis visits.
    u1 = make_user(1, "A", vleermuis=True)
    fake_db = await _fake_db_with_users([u1])

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    async def fake_user_daypart_caps_fn(_db: Any, _week: int):
        return {
            uid: {"Ochtend": 10, "Dag": 10, "Avond": 10, "Flex": 10}
            for uid in [1, 2, 3]
        }

    async def fake_user_caps_fn(_db: Any, _week: int):
        return {uid: 10 for uid in [1, 2, 3]}

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_user_daypart_caps_fn,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities", fake_user_caps_fn
    )
    # This test verifies the 1-visit-per-day coordination rule (non-strict behaviour).
    from core.settings import get_settings as _real_get_settings
    _non_strict = _real_get_settings().model_copy(
        update={"feature_strict_availability": False}
    )
    monkeypatch.setattr(
        "app.services.visit_selection_ortools.get_settings", lambda: _non_strict
    )

    await select_visits_for_week(db=fake_db, week_monday=week_monday)  # type: ignore[arg-type]

    assigned_counts = [
        len(getattr(v, "researchers", [])) for v in (v_morning, v_evening)
    ]
    assert sum(assigned_counts) <= 1


@pytest.mark.asyncio
async def test_users_without_daypart_capacity_rows_not_assigned(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
):
    """Only users with availability rows for the week are considered for assignment.

    We create two eligible users but only provide daypart capacity for one of
    them. Even though both would otherwise qualify, the planner must ignore
    the user without a capacity row and assign visits only to the user that
    has explicit availability.
    """

    async def fake_load_caps(_db: Any, _week: int) -> dict:
        # Global capacity allows both visits to be selected on the daypart.
        return {"Ochtend": 0, "Dag": 2, "Avond": 0, "Flex": 0}

    # Two day visits that can be planned any day in the work week.
    v1 = make_visit(
        vid=4010,
        part_of_day="Dag",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=4),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("Vleermuis", 5)],
    )
    v2 = make_visit(
        vid=4011,
        part_of_day="Dag",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=4),
        required_researchers=1,
        function_names=["X"],
        species_defs=[("Vleermuis", 5)],
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v1, v2]

    # Two eligible users; only user 1 has an availability row for this week.
    u1 = make_user(1, "WithAvailability", vleermuis=True)
    u2 = make_user(2, "WithoutAvailability", vleermuis=True)
    fake_db = await _fake_db_with_users([u1, u2])

    async def fake_user_caps(_db: Any, _week: int) -> dict[int, int]:
        # Both users appear in total capacity for fairness calculations.
        return {1: 2, 2: 2}

    async def fake_user_daypart_caps(_db: Any, _week: int) -> dict[int, dict[str, int]]:
        # Only user 1 has explicit daypart capacity; user 2 has no row.
        return {1: {"Ochtend": 0, "Dag": 2, "Avond": 0, "Flex": 0}}

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities", fake_user_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_user_daypart_caps,
    )

    await select_visits_for_week(db=fake_db, week_monday=week_monday)  # type: ignore[arg-type]

    # Both visits should be assigned to the user that has availability; the
    # user without a capacity row must not receive any assignments.
    assert [u.full_name for u in getattr(v1, "researchers", [])] == ["WithAvailability"]
    assert [u.full_name for u in getattr(v2, "researchers", [])] == ["WithAvailability"]


@pytest.mark.asyncio
async def test_eligible_visits_query_filters_quote_projects(week_monday: date):
    from app.services.visit_planning_selection import _eligible_visits_for_week

    captured_stmt = {}

    class FakeResult:
        def unique(self):
            return self

        def all(self):
            return []

        def scalars(self):
            class S:
                def unique(self_non):
                    return self_non

                def all(self_non):
                    return []

            return S()

    class _AsyncCtx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

    class FakeDB:
        def in_transaction(self) -> bool:
            return False

        def begin(self) -> _AsyncCtx:
            return _AsyncCtx()

        def begin_nested(self) -> _AsyncCtx:
            return _AsyncCtx()

        async def execute(self, stmt):  # type: ignore[no-untyped-def]
            captured_stmt["stmt"] = stmt
            return FakeResult()

    fake_db = FakeDB()

    visits = await _eligible_visits_for_week(fake_db, week_monday)  # type: ignore[arg-type]

    # No rows returned from fake DB
    assert visits == []

    sql_str = str(captured_stmt["stmt"])
    # Ensure the generated query joins the projects table and references the quote flag
    assert "projects" in sql_str
    assert "quote" in sql_str


@pytest.mark.asyncio
async def test_apply_existing_assignments_uses_select_active():
    """Verify that _apply_existing_assignments_to_capacities filters out soft-deleted visits."""

    # Mock DB session
    # We use MagicMock(spec=AsyncSession) because isinstance check requires it.
    # We assign execute as AsyncMock separately.
    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock()

    mock_result = MagicMock()
    # Return empty list to avoid processing logic errors, we only care about the query
    mock_result.scalars.return_value.unique.return_value.all.return_value = []
    db.execute.return_value = mock_result

    # Mock caps dict
    caps = {"Ochtend": 10, "Dag": 5, "Avond": 5, "Flex": 2}
    week = 22

    # Call the function with empty per_user_daypart_caps
    await _apply_existing_assignments_to_capacities(db, week, caps, {})

    # Verify db.execute was called
    assert db.execute.called
    stmt = db.execute.call_args[0][0]

    # Verify "deleted_at IS NULL" is in the generated SQL
    # Simple check: string representation often contains the WHERE clause components
    try:
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    except Exception:
        compiled = str(stmt)

    compiled_lower = compiled.lower()

    # Expect: "visit.deleted_at IS NULL" or similar
    assert "deleted_at" in compiled_lower
    assert "is null" in compiled_lower or "is_null" in compiled_lower
