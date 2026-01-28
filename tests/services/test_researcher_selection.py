from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.visit_planning_selection import select_visits_for_week


def make_visit(
    *,
    vid: int,
    part_of_day: str,
    from_date: date,
    to_date: date,
    required_researchers: int,
    fiets: bool = False,
    project_id: int = 1,
    address: str = "Dest",
) -> Any:
    cluster = SimpleNamespace(project_id=project_id, address=address)
    return SimpleNamespace(
        id=vid,
        part_of_day=part_of_day,
        from_date=from_date,
        to_date=to_date,
        required_researchers=required_researchers,
        priority=False,
        functions=[SimpleNamespace(name="X")],
        species=[
            SimpleNamespace(name="A", family=SimpleNamespace(priority=5, name="fam"))
        ],
        researchers=[],
        fiets=fiets,
        cluster=cluster,
        provisional_week=None,
        provisional_locked=False,
    )


@pytest.fixture()
def week_monday() -> date:
    return date(2025, 6, 2)


class DummyDB:
    async def commit(self) -> None:  # pragma: no cover - trivial
        return None


@pytest.mark.asyncio
async def test_travel_time_scoring_picks_closest(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
) -> None:
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 2, "Dag": 0, "Avond": 0, "Flex": 0}

    v = make_visit(
        vid=1,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=4),
        required_researchers=1,
        address="Dest A",
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v]

    # Two eligible users, different travel times
    u1 = SimpleNamespace(id=1, address="Origin 1")
    u2 = SimpleNamespace(id=2, address="Origin 2")

    async def fake_load_users(_db: Any):
        return [u1, u2]

    async def fake_load_caps_user(_db: Any, _week: int):
        return {1: 5, 2: 5}

    async def fake_travel_minutes(origin: str, destination: str) -> int | None:
        if origin == "Origin 1":
            return 10  # bucket 1
        if origin == "Origin 2":
            return 60  # bucket 4
        return None

    async def fake_load_dp_caps(_db, _week):
        return {
            1: {"Ochtend": 5, "Dag": 5, "Avond": 5, "Flex": 0},
            2: {"Ochtend": 5, "Dag": 5, "Avond": 5, "Flex": 0},
        }

    monkeypatch.setattr(
        "app.services.visit_planning_selection._qualifies_user_for_visit",
        lambda u, v: True,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_all_users", fake_load_users
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities",
        fake_load_caps_user,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_load_dp_caps,
    )
    monkeypatch.setattr(
        "app.services.travel_time.get_travel_minutes", fake_travel_minutes
    )

    result = await select_visits_for_week(db=DummyDB(), week_monday=week_monday)

    # Expect user 1 (shorter travel) assigned
    assert result["selected_visit_ids"] == [1]
    assert len(v.researchers) == 1
    assert getattr(v.researchers[0], "id") == 1


@pytest.mark.asyncio
async def test_excludes_over_75_minutes(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
) -> None:
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0}

    v = make_visit(
        vid=2,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=4),
        required_researchers=1,
        address="Dest B",
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        return [v]

    u1 = SimpleNamespace(id=1, address="Origin A")
    u2 = SimpleNamespace(id=2, address="Origin B")

    async def fake_load_users(_db: Any):
        return [u1, u2]

    async def fake_load_caps_user(_db: Any, _week: int):
        return {1: 5, 2: 5}

    async def fake_travel_minutes(origin: str, destination: str) -> int | None:
        return 80 if origin == "Origin A" else 10

    async def fake_load_dp_caps(_db, _week):
        return {
            1: {"Ochtend": 5, "Dag": 5, "Avond": 5, "Flex": 0},
            2: {"Ochtend": 5, "Dag": 5, "Avond": 5, "Flex": 0},
        }

    monkeypatch.setattr(
        "app.services.visit_planning_selection._qualifies_user_for_visit",
        lambda u, v: True,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_all_users", fake_load_users
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities",
        fake_load_caps_user,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_load_dp_caps,
    )
    monkeypatch.setattr(
        "app.services.travel_time.get_travel_minutes", fake_travel_minutes
    )

    result = await select_visits_for_week(db=DummyDB(), week_monday=week_monday)

    # User 1 excluded, so user 2 gets assigned
    assert result["selected_visit_ids"] == [2]
    assert len(v.researchers) == 1
    assert getattr(v.researchers[0], "id") == 2


@pytest.mark.asyncio
async def test_assigned_capacity_ratio_affects_second_assignment(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
) -> None:
    async def fake_load_caps(_db: Any, _week: int) -> dict:
        return {"Ochtend": 2, "Dag": 0, "Avond": 0, "Flex": 0}

    v1 = make_visit(
        vid=10,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=4),
        required_researchers=1,
        address="Dest C",
    )
    v2 = make_visit(
        vid=11,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=4),
        required_researchers=1,
        address="Dest D",
    )

    async def fake_eligible(_db: Any, _week_monday: date):
        # v1 then v2
        return [v1, v2]

    u1 = SimpleNamespace(id=1, address="O1")
    u2 = SimpleNamespace(id=2, address="O2")

    async def fake_load_users(_db: Any):
        return [u1, u2]

    # Same capacities => after u1 assigned to first visit, its ratio becomes 1/5 and u2 is 0/5
    async def fake_load_caps_user(_db: Any, _week: int):
        return {1: 5, 2: 5}

    # Equal travel times so criterion 2 decides second assignment
    async def fake_travel_minutes(origin: str, destination: str) -> int | None:
        return 10

    async def fake_load_dp_caps(_db, _week):
        return {
            1: {"Ochtend": 5, "Dag": 5, "Avond": 5, "Flex": 0},
            2: {"Ochtend": 5, "Dag": 5, "Avond": 5, "Flex": 0},
        }

    monkeypatch.setattr(
        "app.services.visit_planning_selection._qualifies_user_for_visit",
        lambda u, v: True,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_all_users", fake_load_users
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities",
        fake_load_caps_user,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_load_dp_caps,
    )
    monkeypatch.setattr(
        "app.services.travel_time.get_travel_minutes", fake_travel_minutes
    )

    result = await select_visits_for_week(db=DummyDB(), week_monday=week_monday)

    # Expect user 1 gets v1, user 2 gets v2 due to lower already-assigned ratio
    assert result["selected_visit_ids"] == [10, 11]

    # OR-Tools solver may return symmetric solution (U1->V2, U2->V1) as costs are identical.
    # The important thing is that the load is balanced (different users assigned).
    r1_id = getattr(v1.researchers[0], "id")
    r2_id = getattr(v2.researchers[0], "id")

    # Both must be assigned
    assert r1_id in (1, 2)
    assert r2_id in (1, 2)
    # And they must be different (load balanced)
    assert r1_id != r2_id


@pytest.mark.asyncio
async def test_avoid_multiple_large_team_visits_soft_constraint(
    monkeypatch: pytest.MonkeyPatch, week_monday: date
) -> None:
    # 2 Visits, Size 3.
    v1 = make_visit(
        vid=100,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=4),
        required_researchers=3,
        address="Dest",
    )
    v2 = make_visit(
        vid=101,
        part_of_day="Ochtend",
        from_date=week_monday,
        to_date=week_monday + timedelta(days=4),
        required_researchers=3,
        address="Dest",
    )

    # Users A, B, C (local, 0 travel)
    # Users D, E, F (remote, 20 travel)
    # Capacity: plenty.

    users = []
    for i, name in enumerate(["A", "B", "C", "D", "E", "F"]):
        users.append(SimpleNamespace(id=i + 10, address=name))

    async def fake_travel_minutes(origin: str, destination: str) -> int | None:
        if origin in ["A", "B", "C"]:
            return 0
        if origin in ["D", "E", "F"]:
            return 20
        return 0

    async def fake_eligible(db, wm):
        return [v1, v2]

    async def fake_load_caps(db, w):
        return {"Ochtend": 100, "Dag": 100, "Avond": 100, "Flex": 100}

    async def fake_load_users(db):
        return users

    async def fake_load_user_caps(db, w):
        return {u.id: 10 for u in users}  # plenty

    async def fake_load_dp_caps(db, w):
        return {u.id: {"Ochtend": 10, "Dag": 10, "Avond": 10, "Flex": 0} for u in users}

    # Monkeypatching
    monkeypatch.setattr(
        "app.services.visit_planning_selection._qualifies_user_for_visit",
        lambda u, v: True,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._eligible_visits_for_week", fake_eligible
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_week_capacity", fake_load_caps
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_all_users", fake_load_users
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities",
        fake_load_user_caps,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_load_dp_caps,
    )
    monkeypatch.setattr(
        "app.services.travel_time.get_travel_minutes", fake_travel_minutes
    )

    # Run
    # With FIX (Load Weight 30, Travel 20, Large Penalty 60):
    # Reuse A: Marginal Load 90 + Large Penalty 60 = 150.
    # New D: Marginal Load 30 + Travel 40 = 70.
    # Logic prefers New D (150 > 70).
    # So we expect NO overlap.

    await select_visits_for_week(DummyDB(), week_monday)

    assigned_ids_v1 = [r.id for r in v1.researchers]
    assigned_ids_v2 = [r.id for r in v2.researchers]

    intersection = set(assigned_ids_v1) & set(assigned_ids_v2)
    assert (
        len(intersection) == 0
    ), "Should avoid multiple large visits if travel cost is reasonable (40 < 90+60)"

    # Part 2: Verify it is a SOFT constraint.
    # If travel is very high (e.g. 200), we should accept the penalty and reuse.
    # Reuse A: 150.
    # New D: Load 30 + Travel 200 = 230.
    # 230 > 150 -> Reuse A.

    async def fake_travel_minutes_high(origin: str, destination: str) -> int | None:
        if origin in ["A", "B", "C"]:
            return 0
        if origin in ["D", "E", "F"]:
            return 200
        return 0

    monkeypatch.setattr(
        "app.services.travel_time.get_travel_minutes", fake_travel_minutes_high
    )

    # Must clear researchers to avoid 'planned' interference in this specific test setup
    # (since we are reusing visit objects in memory)
    v1.researchers = []
    v2.researchers = []

    await select_visits_for_week(DummyDB(), week_monday)

    assigned_ids_v1_high = [r.id for r in v1.researchers]
    assigned_ids_v2_high = [r.id for r in v2.researchers]

    intersection_high = set(assigned_ids_v1_high) & set(assigned_ids_v2_high)
    assert (
        len(intersection_high) == 3
    ), "Should reuse researchers if travel cost is prohibitive (230 > 150)"
