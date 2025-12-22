import pytest
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock
from types import SimpleNamespace
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.visit import Visit
from app.models.species import Species
from app.models.family import Family
from app.services.capacity_simulation_service import simulate_capacity_planning
from core.settings import get_settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from uuid import uuid4


@pytest.fixture
async def db(settings_override):
    settings = get_settings()
    # Create a fresh engine to ensure we pick up any overrides if needed,
    # though usually the global one is fine if env is set before import.
    # For safety in tests:
    engine = create_async_engine(settings.sqlalchemy_database_uri_async, echo=False)
    AsyncSessionLocal = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with AsyncSessionLocal() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_simulate_capacity_planning_stateful(monkeypatch: pytest.MonkeyPatch):
    # Setup:
    # Visit 1: Deadline Week 2, requires 1 slot.
    # Visit 2: Deadline Week 3, requires 1 slot.
    from app.models.cluster import Cluster

    start_monday = date(2025, 1, 6)  # Week 2

    fam = Family(name=f"TestFamily-{uuid4()}", priority=1)
    sp = Species(name=f"TestSpecies-{uuid4()}", family_id=1)
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

    async def fake_load_week_capacity(_db, week: int):
        if week == 2:
            return {"Ochtend": 1, "Dag": 0, "Avond": 0, "Flex": 0}
        return {"Ochtend": 0, "Dag": 0, "Avond": 0, "Flex": 0}

    monkeypatch.setattr(
        "app.services.capacity_simulation_service._load_all_open_visits",
        fake_load_all_open_visits,
    )
    monkeypatch.setattr(
        "app.services.capacity_simulation_service._load_week_capacity",
        fake_load_week_capacity,
    )
    
    # Mock user loading required by OR-Tools solver
    async def fake_load_all_users(_db):
        return [] # No users needed if global capacity is sufficient? 
        # Actually OR-Tools needs users to assign.
        # But wait, simulate_capacity_planning checks _consume_capacity (Legacy) or solver?
        # I changed it to use SOLVER.
        # If solver has no users, it cannot assign based on "Required Researchers".
        # Solver constraint: sum(assigned) == req.
        # If no users -> no assignment -> fail.
        # Does stateful simulation assume capacity exists without users?
        # Legacy test setup implies simplistic capacity check.
        # I should provide a dummy user with infinite capacity to satisfy solver.
        pass

    dummy_user = SimpleNamespace(id=1, full_name="Dummy")
    for field in ["smp_huismus", "smp_vleermuis", "smp_gierzwaluw", "vrfg", "hub", "fiets", "wbc", "dvp", "sleutel", "pad", "langoor", "roofvogel", "vleermuis", "zwaluw", "vlinder", "teunisbloempijlstaart", "zangvogel", "biggenkruid", "schijfhoren"]:
        setattr(dummy_user, field, True) # Qualified for everything

    async def fake_load_all_users(_db):
        return [dummy_user]
        
    async def fake_load_user_capacities(_db, _week):
        return {1: 100}
        
    async def fake_load_user_daypart_caps(_db, week: int):
        # Week 2 has capacity (1), others (Week 3) have 0 to force failure
        cap = 1 if week == 2 else 0
        print(f"DEBUG WEEK: {week}, CAP: {cap}")
        return {1: {"Ochtend": cap, "Dag": cap, "Avond": cap, "Flex": 0}}

    monkeypatch.setattr("app.services.visit_planning_selection._load_all_users", fake_load_all_users)
    monkeypatch.setattr("app.services.visit_planning_selection._load_user_capacities", fake_load_user_capacities)
    monkeypatch.setattr("app.services.visit_planning_selection._load_user_daypart_capacities", fake_load_user_daypart_caps)

    # Run simulation
    result = await simulate_capacity_planning(None, start_monday)

    # Verify
    grid = result.grid
    # Structure: grid[family][part][deadline]

    fam_grid = grid.get(fam.name, {})
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


async def _create_user(db, name):
    from app.models.user import User

    u = User(email=f"{name}@example.com", full_name=name)
    db.add(u)
    await db.flush()
    return u
