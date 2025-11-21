import pytest
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.visit import Visit
from app.models.species import Species
from app.models.family import Family
from app.models.availability import AvailabilityWeek
from app.services.capacity_simulation_service import simulate_capacity_planning
from core.settings import get_settings
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from uuid import uuid4

@pytest.fixture
async def db(settings_override):
    settings = get_settings()
    # Create a fresh engine to ensure we pick up any overrides if needed, 
    # though usually the global one is fine if env is set before import.
    # For safety in tests:
    engine = create_async_engine(settings.sqlalchemy_database_uri_async, echo=False)
    AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as session:
        yield session
    
    await engine.dispose()

@pytest.mark.asyncio
async def test_simulate_capacity_planning_stateful(db: AsyncSession):
    # Setup:
    # 1. Create a Family
    fam = Family(name=f"TestFamily-{uuid4()}", priority=1)
    db.add(fam)
    await db.flush()
    
    # 2. Create Species
    sp = Species(name=f"TestSpecies-{uuid4()}", family_id=fam.id)
    db.add(sp)
    await db.flush()
    
    # 2b. Create Project and Cluster
    from app.models.project import Project
    from app.models.cluster import Cluster
    
    proj = Project(code=f"TEST-P-{uuid4()}", location="Test Location", quote=True)
    db.add(proj)
    await db.flush()
    
    clust = Cluster(project_id=proj.id, cluster_number=1, address="Test Address")
    db.add(clust)
    await db.flush()
    
    # 3. Create Visits
    # Visit 1: Deadline Week 2, requires 1 slot.
    # Visit 2: Deadline Week 3, requires 1 slot.
    start_monday = date(2025, 1, 6) # Week 2
    
    v1 = Visit(
        cluster_id=clust.id,
        from_date=date(2025, 1, 1),
        to_date=date(2025, 1, 12), # End of Week 2
        part_of_day="Ochtend",
        required_researchers=1,
    )
    v1.species.append(sp)
    
    v2 = Visit(
        cluster_id=clust.id,
        from_date=date(2025, 1, 1),
        to_date=date(2025, 1, 19), # End of Week 3
        part_of_day="Ochtend",
        required_researchers=1,
    )
    v2.species.append(sp)
    
    db.add_all([v1, v2])
    await db.flush()
    
    # 4. Create Capacity
    # Week 2: 1 slot available (enough for v1)
    # Week 3: 0 slots available (v2 should be unplannable if it wasn't planned in W2)
    # Wait, v2 can be planned in W2 if capacity allows.
    # Let's make W2 have 1 slot. v1 takes it (higher priority due to earlier deadline?).
    # v2 remains.
    # W3 has 0 slots. v2 fails.
    
    # User 1
    u1 = await _create_user(db, f"User-{uuid4()}")
    
    # Week 2 capacity
    aw2 = AvailabilityWeek(
        user_id=u1.id,
        week=2,
        morning_days=2, # 2 slots (1 spare, 1 usable)
        daytime_days=0,
        nighttime_days=0,
        flex_days=0
    )
    db.add(aw2)
    
    # Week 3 capacity (none)
    
    await db.commit()
    
    # Run simulation
    result = await simulate_capacity_planning(db, start_monday)
    
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
