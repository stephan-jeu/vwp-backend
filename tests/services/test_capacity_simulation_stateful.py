import pytest
from datetime import date
from types import SimpleNamespace

from app.models.visit import Visit
from app.models.species import Species
from app.models.family import Family
from app.services.capacity_simulation_service import simulate_capacity_planning


@pytest.mark.asyncio
async def test_simulate_capacity_planning_stateful(monkeypatch: pytest.MonkeyPatch):
    # Setup:
    # Visit 1: Deadline Week 2, requires 1 slot.
    # Visit 2: Deadline Week 3, requires 1 slot.
    from app.models.cluster import Cluster

    start_monday = date(2025, 1, 6)  # Week 2

    fam = Family(name="Vleermuis", priority=1)
    sp = Species(name="TestSpecies", family_id=1)
    sp.family = fam
    clust = Cluster(project_id=1, cluster_number=1, address="Test Address")

    v1 = Visit(
        cluster_id=clust.id,
        from_date=date(2025, 1, 1),
        to_date=date(2025, 1, 12),  # End of Week 2
        part_of_day="Ochtend",
        required_researchers=1,
    )
    v1.species = [sp]

    v2 = Visit(
        cluster_id=clust.id,
        from_date=date(2025, 1, 1),
        to_date=date(2025, 1, 19),  # End of Week 3
        part_of_day="Ochtend",
        required_researchers=1,
    )
    v2.species = [sp]

    async def fake_load_all_open_visits(_db, _start_date):
        return [v1, v2]

    monkeypatch.setattr(
        "app.services.capacity_simulation_service._load_all_open_visits",
        fake_load_all_open_visits,
    )

    dummy_user = SimpleNamespace(id=1, full_name="Dummy")
    for field in [
        "smp_huismus",
        "smp_vleermuis",
        "smp_gierzwaluw",
        "vrfg",
        "hub",
        "fiets",
        "wbc",
        "dvp",
        "sleutel",
        "pad",
        "langoor",
        "roofvogel",
        "vleermuis",
        "zwaluw",
        "vlinder",
        "teunisbloempijlstaart",
        "zangvogel",
        "biggenkruid",
        "schijfhoren",
    ]:
        setattr(dummy_user, field, True)  # Qualified for everything

    async def fake_load_all_users(_db):
        return [dummy_user]

    async def fake_load_user_capacities(_db, _week):
        return {1: 100}

    async def fake_load_user_daypart_caps(_db, week: int):
        # Week 2 has capacity (1), others (Week 3) have 0 to force failure
        cap = 1 if week == 2 else 0
        return {1: {"Ochtend": cap, "Dag": cap, "Avond": cap, "Flex": 0}}

    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_all_users", fake_load_all_users
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_capacities",
        fake_load_user_capacities,
    )
    monkeypatch.setattr(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        fake_load_user_daypart_caps,
    )

    async def fake_select_visits_cp_sat(
        _db,
        week_monday,
        *,
        visits,
        users,
        user_caps,
        user_daypart_caps,
        timeout_seconds,
        include_travel_time,
        ignore_existing_assignments,
    ):
        if week_monday.isocalendar().week == 2:
            v1.researchers = [dummy_user]
            return SimpleNamespace(selected=[v1], skipped=[])

        if week_monday.isocalendar().week == 3:
            v2.researchers = []
            return SimpleNamespace(selected=[], skipped=[v2])

        return SimpleNamespace(selected=[], skipped=[])

    monkeypatch.setattr(
        "app.services.capacity_simulation_service.select_visits_cp_sat",
        fake_select_visits_cp_sat,
    )

    class _FakeScalars:
        def unique(self):
            return self

        def all(self):
            return []

    class _FakeResult:
        def scalars(self):
            return _FakeScalars()

        def scalar_one_or_none(self):
            return None

        def unique(self):
            return self

        def all(self):
            return []

    class _FakeDB:
        def add(self, _obj):
            return None

        async def commit(self):
            return None

        async def flush(self):
            return None

        async def refresh(self, _obj):
            return None

        async def execute(self, _stmt):  # type: ignore[no-untyped-def]
            return _FakeResult()

    # Run simulation
    result = await simulate_capacity_planning(_FakeDB(), start_monday)

    # Verify
    grid = result.grid
    # Structure: grid[family][part][deadline]

    # The service capitalizes the family name for the user flag label
    expected_key = fam.name.strip().lower().capitalize()
    fam_grid = grid.get(expected_key, {})
    part_grid = fam_grid.get("Ochtend", {})

    # v1 deadline is "2025-01-12"
    # v2 deadline is "2025-01-19"

    cell_w2 = part_grid.get("2025-01-12")
    cell_w3 = part_grid.get("2025-01-19")

    assert cell_w2 is not None
    assert cell_w3 is not None

    # v1 should be planned in W2.
    # v2 could be planned in W2 if capacity was 2. But it is 1.
    # So v1 takes it. v2 moves to W3.
    # W3 has 0 capacity. v2 is unplannable.

    # cell_w2: planned=1 (v1), unplannable=0
    assert cell_w2.assigned == 1
    assert cell_w2.shortfall == 0

    # cell_w3: planned=0, unplannable=1 (v2)
    assert cell_w3.assigned == 0
    assert cell_w3.shortfall == 1
