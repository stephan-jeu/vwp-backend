from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from app.services.visit_planning_selection import select_visits_for_week


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

    # Create fake rows with totals: morning=3, day=3, night=3, flex=2
    rows = [
        SimpleNamespace(morning_days=2, daytime_days=1, nighttime_days=1, flex_days=1),
        SimpleNamespace(morning_days=1, daytime_days=2, nighttime_days=2, flex_days=1),
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
        "grote_vos": False,
        "iepenpage": False,
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
        sleutel=True,
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

    await select_visits_for_week(db=fake_db, week_monday=week_monday)  # type: ignore[arg-type]

    assert [u.full_name for u in getattr(v, "researchers", [])] == ["B"]


@pytest.mark.asyncio
async def test_do_not_reuse_user_across_visits(
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

    # Only one eligible user; ensure they get assigned to only one visit
    u1 = make_user(1, "A", vleermuis=True)
    u2 = make_user(2, "B", vleermuis=False)
    fake_db = await _fake_db_with_users([u1, u2])

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )

    await select_visits_for_week(db=fake_db, week_monday=week_monday)  # type: ignore[arg-type]

    counts = [len(getattr(v, "researchers", [])) for v in (v1, v2)]
    assert sorted(counts) == [0, 1]


@pytest.mark.asyncio
async def test_eligible_visits_query_filters_quote_projects(week_monday: date):
    from app.services.visit_planning_selection import _eligible_visits_for_week

    captured_stmt = {}

    class FakeResult:
        def scalars(self):
            class S:
                def unique(self_non):
                    return self_non

                def all(self_non):
                    return []

            return S()

    class FakeDB:
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
