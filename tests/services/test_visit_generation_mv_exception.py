import pytest
import pytest_asyncio
from datetime import date
from app.models.family import Family
from app.models.species import Species
from app.models.function import Function
from app.models.protocol import Protocol
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.cluster import Cluster
from app.services.visit_generation import generate_visits_for_cluster

class _FakeScalars:
    def __init__(self, items):
        self._items = items
    def unique(self): return self
    def all(self): return self._items

class _FakeResult:
    def __init__(self, items):
        self._items = items
    def scalars(self): return _FakeScalars(self._items)
    def first(self): return None

class _FakeSession:
    async def execute(self, _stmt): return _FakeResult([])
    def add(self, _obj): pass
    async def flush(self): pass

def _make_protocol(proto_id, fn_name, sp_abbr, start_ref="SUNSET", requires_morning=False, requires_evening=False):
    fam = Family(id=1, name="Fam", priority=1)
    sp = Species(id=proto_id*10, family_id=1, name="Spec", abbreviation=sp_abbr)
    sp.family = fam
    fn = Function(id=proto_id*100, name=fn_name)
    
    p = Protocol(
        id=proto_id,
        species_id=sp.id,
        function_id=fn.id,
        start_timing_reference=start_ref,
        requires_morning_visit=requires_morning,
        requires_evening_visit=requires_evening,
        visit_duration_hours=2.0
    )
    p.species = sp
    p.function = fn
    w = ProtocolVisitWindow(
        id=proto_id,
        protocol_id=proto_id,
        visit_index=1,
        window_from=date(2025, 5, 1),
        window_to=date(2025, 6, 1),
        required=True
    )
    p.visit_windows = [w]
    return p

@pytest.mark.asyncio
async def test_paarverblijf_mv_ochtend_exception(mocker):
    # Ochtend case -> "3 uur voor zonsondergang"
    p = _make_protocol(1, "Paarverblijf", "MV", start_ref="SUNRISE", requires_morning=True)
    
    fake_db = _FakeSession()
    
    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql: return _FakeResult([p])
        return _FakeResult([p.function, p.species])
        
    fake_db.execute = exec_stub
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    
    cluster = Cluster(id=1, project_id=1, address="addr", cluster_number=1)
    
    visits, _ = await generate_visits_for_cluster(
        fake_db, cluster, function_ids=[p.function.id], species_ids=[p.species.id]
    )
    
    assert len(visits) > 0
    assert visits[0].part_of_day == "Ochtend"
    # Logic in generate_visits_for_cluster might default to something else currently
    # We expect this to FAIL currently, and PASS after fix.
    # Current behavior for SUNRISE Ochtend is "Zonsopkomst" or similar
    assert visits[0].start_time_text == "3 uur voor zonsopgang"

@pytest.mark.asyncio
async def test_paarverblijf_mv_avond_exception(mocker):
    # Avond case -> "Zonsopgang"
    p = _make_protocol(2, "Paarverblijf", "MV", start_ref="SUNSET", requires_evening=True)
    
    fake_db = _FakeSession()
    
    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql: return _FakeResult([p])
        return _FakeResult([p.function, p.species])
        
    fake_db.execute = exec_stub
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    
    cluster = Cluster(id=2, project_id=1, address="addr", cluster_number=1)
    
    visits, _ = await generate_visits_for_cluster(
        fake_db, cluster, function_ids=[p.function.id], species_ids=[p.species.id]
    )
    
    assert len(visits) > 0
    assert visits[0].part_of_day == "Avond"
    # We expect this to FAIL currently
    assert visits[0].start_time_text == "Zonsondergang"
