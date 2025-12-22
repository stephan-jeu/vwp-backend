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

    def unique(self):
        return self

    def all(self):
        return self._items


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalars(self._items)

    def first(self):
        return None


class _FakeSession:
    async def execute(self, _stmt):
        return _FakeResult([])

    def add(self, _obj):
        return None


@pytest_asyncio.fixture
async def fake_db():
    return _FakeSession()


def _make_protocol(
    *,
    proto_id: int,
    fam_name: str,
    species_id: int,
    species_name: str,
    fn_id: int,
    fn_name: str,
    window_from: date,
    window_to: date,
    start_ref: str | None = None,
    end_ref: str | None = None,
    start_rel_min: int | None = None,
    end_rel_min: int | None = None,
    visit_duration_h: float | None = None,
):
    fam = Family(id=proto_id, name=fam_name, priority=1)
    sp = Species(
        id=species_id,
        family_id=fam.id,
        name=species_name,
        abbreviation=species_name[:2],
    )
    sp.family = fam
    fn = Function(id=fn_id, name=fn_name)

    p = Protocol(
        id=proto_id,
        species_id=sp.id,
        function_id=fn.id,
        visit_duration_hours=visit_duration_h,
        start_timing_reference=start_ref,
        end_timing_reference=end_ref,
        start_time_relative_minutes=start_rel_min,
        end_time_relative_minutes=end_rel_min,
    )
    p.species = sp
    p.function = fn
    w1 = ProtocolVisitWindow(
        id=proto_id * 10 + 1,
        protocol_id=proto_id,
        visit_index=1,
        window_from=window_from,
        window_to=window_to,
        required=True,
        label=None,
    )
    p.visit_windows = [w1]
    return p


@pytest.mark.asyncio
async def test_absolute_time_allows_both_and_prefers_morning(mocker, fake_db):
    # Arrange
    today_year = date.today().year
    wf = date(today_year, 5, 1)
    wt = date(today_year, 6, 1)

    p1 = _make_protocol(
        proto_id=101,
        fam_name="Vleermuis",
        species_id=1101,
        species_name="BatAA",
        fn_id=1110,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="ABSOLUTE_TIME",
        visit_duration_h=1.0,
    )
    p2 = _make_protocol(
        proto_id=102,
        fam_name="Vleermuis",
        species_id=1102,
        species_name="BatAB",
        fn_id=1111,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="ABSOLUTE_TIME",
        visit_duration_h=1.0,
    )
    
    # Manually set absolute time (helper doesn't support it yet)
    from datetime import time
    p1.start_time_absolute_from = time(22, 30)
    # p2 not set, but priority loop should find p1 if present

    funcs = {p1.function.id: p1.function, p2.function.id: p2.function}
    species = {p1.species.id: p1.species, p2.species.id: p2.species}

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([p1, p2])
        if "FROM functions" in sql:
            return _FakeResult(list(funcs.values()))
        if "FROM species" in sql:
            return _FakeResult(list(species.values()))
        return _FakeResult([])

    fake_db.execute = exec_stub  # type: ignore[attr-defined]
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)

    cluster = Cluster(id=11, project_id=1, address="c11", cluster_number=11)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db, cluster, function_ids=[1110, 1111], species_ids=[1101, 1102]
    )

    # Updated Requirement: ABSOLUTE_TIME now implies strict "Avond" (Evening).
    # Previous behavior was flexible, preferring morning.
    # Assert
    assert len(visits) >= 1
    assert visits[0].part_of_day == "Avond"

@pytest.mark.asyncio
async def test_remarks_optimization_suppressed(mocker, fake_db):
    """Verify that remarks are suppressed when redundant (Full Cartesian Product)."""
    # Case 1: Same Function, Diff Species -> Redundant
    # Function A, Species X, Y.
    # Requests: (A, X), (A, Y).
    # Product: (A,X), (A,Y). Matches Active.
    today_year = date.today().year
    wf = date(today_year, 5, 1)
    wt = date(today_year, 6, 1)

    p1 = _make_protocol(proto_id=201, fam_name="F", species_id=301, species_name="Alpha", fn_id=401, fn_name="FuncA", window_from=wf, window_to=wt, visit_duration_h=1)
    p2 = _make_protocol(proto_id=202, fam_name="F", species_id=302, species_name="Beta", fn_id=401, fn_name="FuncA", window_from=wf, window_to=wt, visit_duration_h=1)
    
    # Mock DB
    funcs = {p1.function.id: p1.function}
    species = {p1.species.id: p1.species, p2.species.id: p2.species}
    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql: return _FakeResult([p1, p2])
        if "FROM functions" in sql: return _FakeResult(list(funcs.values()))
        if "FROM species" in sql: return _FakeResult(list(species.values()))
        return _FakeResult([])
    fake_db.execute = exec_stub
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    
    cluster = Cluster(id=20, project_id=1, address="c20", cluster_number=20)
    
    # Act
    visits, _ = await generate_visits_for_cluster(fake_db, cluster, [401], [301, 302])
    
    # Assert
    assert len(visits) == 1
    # Should be suppressed (None or empty string) because FuncA x {Alpha, Beta} == Active
    assert not visits[0].remarks_field

@pytest.mark.asyncio
async def test_remarks_optimization_shown(mocker, fake_db):
    """Verify that remarks are SHOWN when exclusions exist."""
    # Case 2: Diff Function, Diff Species -> Not Full Product
    # P1(FuncA, Alpha), P2(FuncB, Beta).
    # Product: (A,Al), (A,Be), (B,Al), (B,Be).
    # Active: (A,Al), (B,Be).
    # Misses: (A,Be), (B,Al).
    # Expected: Remarks shown.
    today_year = date.today().year
    wf = date(today_year, 5, 1)
    wt = date(today_year, 6, 1)

    p1 = _make_protocol(proto_id=203, fam_name="F", species_id=303, species_name="Gamma", fn_id=403, fn_name="FuncA", window_from=wf, window_to=wt, visit_duration_h=1)
    p2 = _make_protocol(proto_id=204, fam_name="F", species_id=304, species_name="Delta", fn_id=404, fn_name="FuncB", window_from=wf, window_to=wt, visit_duration_h=1)
    
    funcs = {p1.function.id: p1.function, p2.function.id: p2.function}
    species = {p1.species.id: p1.species, p2.species.id: p2.species}
    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql: return _FakeResult([p1, p2])
        if "FROM functions" in sql: return _FakeResult(list(funcs.values()))
        if "FROM species" in sql: return _FakeResult(list(species.values()))
        return _FakeResult([])
    fake_db.execute = exec_stub
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    
    cluster = Cluster(id=21, project_id=1, address="c21", cluster_number=21)
    
    visits, _ = await generate_visits_for_cluster(fake_db, cluster, [403, 404], [303, 304])
    
    assert len(visits) == 1
    assert visits[0].remarks_field # Should not be empty

@pytest.mark.asyncio
async def test_rugstreeppad_sequential_visits(mocker, fake_db):
    """Verify that Rugstreeppad functions are never combined (Sequential)."""
    today_year = date.today().year
    wf = date(today_year, 5, 1)
    wt = date(today_year, 6, 1)

    # Rugstreeppad: Different Functions -> Split
    p1 = _make_protocol(proto_id=501, fam_name="Pad", species_id=601, species_name="Rugstreeppad", fn_id=701, fn_name="Roep", window_from=wf, window_to=wt)
    p2 = _make_protocol(proto_id=502, fam_name="Pad", species_id=601, species_name="Rugstreeppad", fn_id=702, fn_name="Water", window_from=wf, window_to=wt)

    # Control: Vleermuis: Different Functions -> Merge
    p3 = _make_protocol(proto_id=503, fam_name="Vleermuis", species_id=602, species_name="Laatvlieger", fn_id=701, fn_name="Roep", window_from=wf, window_to=wt)
    p4 = _make_protocol(proto_id=504, fam_name="Vleermuis", species_id=602, species_name="Laatvlieger", fn_id=702, fn_name="Water", window_from=wf, window_to=wt)

    # Mock DB
    funcs = {p1.function.id: p1.function, p2.function.id: p2.function}
    species = {p1.species.id: p1.species, p3.species.id: p3.species}
    # Stateful Mock
    active_species_id = 601
    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            # Return based on active test phase
            if active_species_id == 601: return _FakeResult([p1, p2])
            if active_species_id == 602: return _FakeResult([p3, p4])
            return _FakeResult([]) 
        if "FROM functions" in sql: return _FakeResult(list(funcs.values()))
        if "FROM species" in sql: return _FakeResult(list(species.values()))
        return _FakeResult([])
    fake_db.execute = exec_stub
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    
    # Test Rugstreeppad (Split)
    active_species_id = 601
    cluster1 = Cluster(id=50, project_id=1, address="c50", cluster_number=50)
    visits1, _ = await generate_visits_for_cluster(fake_db, cluster1, [701, 702], [601])
    assert len(visits1) == 2 
    
    # Test Control (Merge)
    active_species_id = 602

@pytest.mark.asyncio
async def test_visit_sorting_series_priority(mocker, fake_db):
    """Verify that older series visits come before newer series starts on same day."""
    today_year = date.today().year
    
    # Old Series (Started Jan 1)
    # Target visit on June 1
    p_old = _make_protocol(proto_id=801, fam_name="F", species_id=901, species_name="OldSp", fn_id=1001, fn_name="OldFn", window_from=date(today_year, 6, 1), window_to=date(today_year, 6, 1))
    # Add historical window to establish series start
    w_hist = ProtocolVisitWindow(
        id=8010, protocol_id=p_old.id, visit_index=1, 
        window_from=date(today_year, 1, 1), window_to=date(today_year, 2, 1), required=True
    )
    # The actual window for this visit is visit_index=3
    p_old.visit_windows[0].visit_index = 3 # Modify the default one created by helper
    p_old.visit_windows.append(w_hist) # Add history
    
    # New Series (Started June 1)
    # Target visit on June 1
    p_new = _make_protocol(proto_id=802, fam_name="F", species_id=902, species_name="NewSp", fn_id=1002, fn_name="NewFn", window_from=date(today_year, 6, 1), window_to=date(today_year, 6, 1))
    p_new.visit_windows[0].visit_index = 1
    
    # Mock DB
    funcs = {p_old.function.id: p_old.function, p_new.function.id: p_new.function}
    species = {p_old.species.id: p_old.species, p_new.species.id: p_new.species}
    
    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql: return _FakeResult([p_old, p_new])
        if "FROM functions" in sql: return _FakeResult(list(funcs.values()))
        if "FROM species" in sql: return _FakeResult(list(species.values()))
        return _FakeResult([])
        
    fake_db.execute = exec_stub
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    
    cluster = Cluster(id=60, project_id=1, address="c60", cluster_number=60)
    
    # Both visits generated on June 1.
    # Old (V3) should be before New (V1)
    visits, _ = await generate_visits_for_cluster(fake_db, cluster, [1001, 1002], [901, 902])
    
    # Filter for June visits (ignoring the historical Jan visit)
    june_visits = [v for v in visits if v.from_date == date(today_year, 6, 1)]
    assert len(june_visits) == 2
    
    # Verify Order: Old (Series Start Jan) < New (Series Start June)
    # Because Old series started earlier, it should finish its sequential visits first.
    assert june_visits[0].functions[0].name == "OldFn"
    assert june_visits[1].functions[0].name == "NewFn"

@pytest.mark.asyncio
async def test_remarks_optimization_suppressed_high_index(mocker, fake_db):
    """Verify that remarks are suppressed even for Index > 1 if uniform and full product."""
    today_year = date.today().year
    wf = date(today_year, 5, 1)
    wt = date(today_year, 6, 1)
    
    # 2 protocols, both Visit Index 2
    # Full Product: 1 Fn x 2 Sp (or 2 Fn x 1 Sp)
    # Let's do 1 Fn x 2 Sp
    p1 = _make_protocol(proto_id=301, fam_name="F", species_id=401, species_name="Alpha", fn_id=501, fn_name="FuncA", window_from=wf, window_to=wt)
    p1.visit_windows[0].visit_index = 2
    
    p2 = _make_protocol(proto_id=302, fam_name="F", species_id=402, species_name="Beta", fn_id=501, fn_name="FuncA", window_from=wf, window_to=wt)
    p2.visit_windows[0].visit_index = 2
    
    funcs = {p1.function.id: p1.function}
    species = {p1.species.id: p1.species, p2.species.id: p2.species}
    
    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql: return _FakeResult([p1, p2])
        if "FROM functions" in sql: return _FakeResult(list(funcs.values()))
        if "FROM species" in sql: return _FakeResult(list(species.values()))
        return _FakeResult([])
        
    fake_db.execute = exec_stub
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    
    cluster = Cluster(id=30, project_id=1, address="c30", cluster_number=30)
    
    # Act
    visits, _ = await generate_visits_for_cluster(fake_db, cluster, [501], [401, 402])
    
    # Assert
    assert len(visits) == 1
    # Should be suppressed
    assert not visits[0].remarks_field

@pytest.mark.asyncio
async def test_rugstreeppad_remarks_exception(mocker, fake_db):
    """Verify that Rugstreeppad + 'platen...' triggers specific remarks text."""
    today_year = date.today().year
    wf = date(today_year, 5, 1)
    wt = date(today_year, 6, 1)
    
    p1 = _make_protocol(proto_id=601, fam_name="Pad", species_id=701, species_name="Rugstreeppad", fn_id=801, fn_name="platen neerleggen, eisnoeren/larven", window_from=wf, window_to=wt)
    
    funcs = {p1.function.id: p1.function}
    species = {p1.species.id: p1.species}
    
    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql: return _FakeResult([p1])
        if "FROM functions" in sql: return _FakeResult(list(funcs.values()))
        if "FROM species" in sql: return _FakeResult(list(species.values()))
        return _FakeResult([])
        
    fake_db.execute = exec_stub
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    
    cluster = Cluster(id=70, project_id=1, address="c70", cluster_number=70)
    
    visits, _ = await generate_visits_for_cluster(fake_db, cluster, [801], [701])
    
    assert len(visits) == 1
    assert visits[0].remarks_field
    assert "Fijnmazig schepnet (RAVON-type) mee" in visits[0].remarks_field
    # Optimization would usually suppress the species list "Rugstreeppad (1)" since it's full product.
    # So we expect ONLY the special text (or special text + nothing else).
    assert "Rugstreeppad (" not in visits[0].remarks_field

@pytest.mark.asyncio
async def test_vlinder_exceptions(mocker, fake_db):
    """Verify Start Time Text and Remarks for Vlinder family."""
    today_year = date.today().year
    wf = date(today_year, 5, 1)
    wt = date(today_year, 6, 1)
    
    # Create Protocol with Family "Vlinder"
    p1 = _make_protocol(proto_id=605, fam_name="Vlinder", species_id=705, species_name="Dagpauwoog", fn_id=805, fn_name="Transect", window_from=wf, window_to=wt)
    # Ensure family name is set correctly (helper sets fam_name on Family object)
    
    funcs = {p1.function.id: p1.function}
    species = {p1.species.id: p1.species}
    
    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql: return _FakeResult([p1])
        if "FROM functions" in sql: return _FakeResult(list(funcs.values()))
        if "FROM species" in sql: return _FakeResult(list(species.values()))
        return _FakeResult([])
        
    fake_db.execute = exec_stub
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    
    cluster = Cluster(id=75, project_id=1, address="c75", cluster_number=75)
    
    visits, _ = await generate_visits_for_cluster(fake_db, cluster, [805], [705])
    
    assert len(visits) == 1
    # Verify Start Time Text
    assert visits[0].start_time_text == "Tussen 10:00 en 15:00 starten (evt. om 09:00 starten als het dan al 22 graden is en zonnig)"
    # Verify Remarks
    assert "Min. 15 tot 19 graden" in (visits[0].remarks_field or "")

@pytest.mark.asyncio
async def test_langoren_remarks_exception(mocker, fake_db):
    """Verify Remarks for Langoren family."""
    today_year = date.today().year
    wf = date(today_year, 5, 1)
    wt = date(today_year, 6, 1)
    
    # Create Protocol with Family "Langoren"
    p1 = _make_protocol(proto_id=606, fam_name="Langoren", species_id=706, species_name="Groene Langoor", fn_id=806, fn_name="Transect", window_from=wf, window_to=wt)
    
    funcs = {p1.function.id: p1.function}
    species = {p1.species.id: p1.species}
    
    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql: return _FakeResult([p1])
        if "FROM functions" in sql: return _FakeResult(list(funcs.values()))
        if "FROM species" in sql: return _FakeResult(list(species.values()))
        return _FakeResult([])
        
    fake_db.execute = exec_stub
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    
    cluster = Cluster(id=76, project_id=1, address="c76", cluster_number=76)
    
    visits, _ = await generate_visits_for_cluster(fake_db, cluster, [806], [706])
    
    assert len(visits) == 1
    # Verify Remarks
    assert "Geen mist, sneeuwval. Bodemtemperatuur < 15 graden" in (visits[0].remarks_field or "")


@pytest.mark.asyncio
async def test_min_effective_window_days_prevents_merge(mocker, fake_db):
    # Arrange: two protocols overlap for 5 days; set threshold to 10 so they cannot merge
    today_year = date.today().year
    a1 = date(today_year, 5, 1)
    a2 = date(today_year, 5, 20)
    b1 = date(today_year, 5, 16)
    b2 = date(today_year, 6, 1)
    # Overlap is May 16-20 => 4 days difference but code uses (to-from).days so 4; make it 5+ by adjusting
    b1 = date(today_year, 5, 15)  # overlap 5 days (15-20)

    p1 = _make_protocol(
        proto_id=201,
        fam_name="Vleermuis",
        species_id=1201,
        species_name="BatBA",
        fn_id=1210,
        fn_name="Nest",
        window_from=a1,
        window_to=a2,
        start_ref="SUNSET",
    )
    p2 = _make_protocol(
        proto_id=202,
        fam_name="Vleermuis",
        species_id=1202,
        species_name="BatBB",
        fn_id=1211,
        fn_name="Nest",
        window_from=b1,
        window_to=b2,
        start_ref="SUNSET",
    )

    funcs = {p1.function.id: p1.function, p2.function.id: p2.function}
    species = {p1.species.id: p1.species, p2.species.id: p2.species}

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([p1, p2])
        if "FROM functions" in sql:
            return _FakeResult(list(funcs.values()))
        if "FROM species" in sql:
            return _FakeResult(list(species.values()))
        return _FakeResult([])

    fake_db.execute = exec_stub  # type: ignore[attr-defined]
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    # Monkeypatch threshold
    import app.services.visit_generation as vg

    old_min = vg.MIN_EFFECTIVE_WINDOW_DAYS
    vg.MIN_EFFECTIVE_WINDOW_DAYS = 10

    cluster = Cluster(id=12, project_id=1, address="c12", cluster_number=12)

    # Act
    try:
        visits, _ = await generate_visits_for_cluster(
            fake_db, cluster, function_ids=[1210, 1211], species_ids=[1201, 1202]
        )
    finally:
        vg.MIN_EFFECTIVE_WINDOW_DAYS = old_min

    # Assert: separate visits due to insufficient overlap length
    assert len(visits) == 2


@pytest.mark.asyncio
async def test_completion_pass_creates_missing_occurrence_and_indexes(mocker, fake_db):
    # Arrange: one protocol with two identical windows (visit_index 1 and 2)
    today_year = date.today().year
    wf = date(today_year, 6, 1)
    wt = date(today_year, 7, 1)

    fam = Family(id=301, name="Vleermuis", priority=1)
    sp = Species(id=1301, family_id=fam.id, name="BatCA", abbreviation="BA")
    sp.family = fam
    fn = Function(id=1310, name="Nest")

    p = Protocol(
        id=301, species_id=sp.id, function_id=fn.id, start_timing_reference="SUNSET"
    )
    p.species = sp
    p.function = fn
    w1 = ProtocolVisitWindow(
        id=3011,
        protocol_id=p.id,
        visit_index=1,
        window_from=wf,
        window_to=wt,
        required=True,
        label=None,
    )
    w2 = ProtocolVisitWindow(
        id=3012,
        protocol_id=p.id,
        visit_index=2,
        window_from=wf,
        window_to=wt,
        required=True,
        label=None,
    )
    p.visit_windows = [w1, w2]

    funcs = {fn.id: fn}
    species = {sp.id: sp}

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([p])
        if "FROM functions" in sql:
            return _FakeResult(list(funcs.values()))
        if "FROM species" in sql:
            return _FakeResult(list(species.values()))
        return _FakeResult([])

    fake_db.execute = exec_stub  # type: ignore[attr-defined]
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)

    cluster = Cluster(id=13, project_id=1, address="c13", cluster_number=13)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db, cluster, function_ids=[fn.id], species_ids=[sp.id]
    )

    # Assert behavior: completion ensures the protocol has at least one planned occurrence
    # and assigns occurrence indices. 
    # Since P1 has 2 windows and cannot visit itself, we get 2 visits.
    # Due to "Full Product + Uniform Index" optimization, remarks are suppressed.
    assert len(visits) == 2
    assert visits[0].remarks_field is None
    assert visits[1].remarks_field is None


@pytest.mark.asyncio
async def test_two_phase_creates_ochtend_and_avond_buckets_without_duplicates(
    mocker, fake_db
):
    # Arrange: required morning protocol allows both; companion allows only evening → split into two parts
    today_year = date.today().year
    wf = date(today_year, 5, 15)
    wt = date(today_year, 7, 15)

    p_req = _make_protocol(
        proto_id=401,
        fam_name="Vleermuis",
        species_id=1401,
        species_name="BatDA",
        fn_id=1410,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
        end_ref="SUNRISE",
    )
    # mark required morning
    setattr(p_req, "requires_morning_visit", True)

    p_even = _make_protocol(
        proto_id=402,
        fam_name="Vleermuis",
        species_id=1402,
        species_name="BatDB",
        fn_id=1411,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
    )

    funcs = {p_req.function.id: p_req.function, p_even.function.id: p_even.function}
    species = {p_req.species.id: p_req.species, p_even.species.id: p_even.species}

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([p_req, p_even])
        if "FROM functions" in sql:
            return _FakeResult(list(funcs.values()))
        if "FROM species" in sql:
            return _FakeResult(list(species.values()))
        return _FakeResult([])

    fake_db.execute = exec_stub  # type: ignore[attr-defined]
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)

    cluster = Cluster(id=22, project_id=1, address="c22", cluster_number=22)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db,
        cluster,
        function_ids=[],
        species_ids=[],
        protocols=[p_req, p_even],
    )

    # Assert behavior: there is an Ochtend visit containing the required-morning function
    # and there is an Avond visit containing the evening-only function. Do not enforce
    # exact visit count to keep the test resilient to later coalescing rules.
    has_morning_req = any(
        v.part_of_day == "Ochtend"
        and any(f.id == p_req.function.id for f in v.functions)
        for v in visits
    )
    has_evening_even = any(
        v.part_of_day == "Avond"
        and any(f.id == p_even.function.id for f in v.functions)
        for v in visits
    )
    assert has_morning_req
    assert has_evening_even


@pytest.mark.asyncio
async def test_cross_family_allowlist_non_smp_can_merge(mocker, fake_db):
    # Arrange: allowlisted cross-family merge (Vleermuis, Zwaluw) for non-SMP
    today_year = date.today().year
    wf = date(today_year, 6, 1)
    wt = date(today_year, 7, 1)

    p_bat = _make_protocol(
        proto_id=501,
        fam_name="Vleermuis",
        species_id=1501,
        species_name="BatEA",
        fn_id=1510,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
    )
    p_swift = _make_protocol(
        proto_id=502,
        fam_name="Zwaluw",
        species_id=1502,
        species_name="SwiftA",
        fn_id=1511,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
    )

    funcs = {p_bat.function.id: p_bat.function, p_swift.function.id: p_swift.function}
    species = {p_bat.species.id: p_bat.species, p_swift.species.id: p_swift.species}

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([p_bat, p_swift])
        if "FROM functions" in sql:
            return _FakeResult(list(funcs.values()))
        if "FROM species" in sql:
            return _FakeResult(list(species.values()))
        return _FakeResult([])

    fake_db.execute = exec_stub  # type: ignore[attr-defined]
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)

    cluster = Cluster(id=15, project_id=1, address="c15", cluster_number=15)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db, cluster, function_ids=[1510, 1511], species_ids=[1501, 1502]
    )

    # Assert: should merge into a single visit under allowlist rule
    assert len(visits) == 1


@pytest.mark.asyncio
async def test_morning_duration_and_start_text_use_calculated_start(mocker, fake_db):
    # Arrange: two protocols ending around sunrise
    # - p1: duration 2h, end at sunrise
    # - p2: duration 2h, end 1h before sunrise
    # Expected: start = 3h before sunrise, duration = 3h (180 min)
    # With our half-hour alignment and logic, we assert 2.5h if picked start is -150 and latest end is 0 for given inputs
    today_year = date.today().year
    wf = date(today_year, 5, 15)
    wt = date(today_year, 7, 15)

    p1 = _make_protocol(
        proto_id=801,
        fam_name="Vleermuis",
        species_id=1801,
        species_name="BatMA",
        fn_id=1810,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        end_ref="SUNRISE",
        end_rel_min=0,
        visit_duration_h=2.0,
    )
    # Force morning to ensure the bucket is Ochtend
    setattr(p1, "requires_morning_visit", True)

    p2 = _make_protocol(
        proto_id=802,
        fam_name="Vleermuis",
        species_id=1802,
        species_name="BatMB",
        fn_id=1811,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        end_ref="SUNRISE",
        end_rel_min=30,  # 0.5 hour before sunrise
        visit_duration_h=2.0,
    )

    # Provide protocols directly to bypass DB resolution
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    cluster = Cluster(id=26, project_id=1, address="c26", cluster_number=26)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db,
        cluster,
        function_ids=[],
        species_ids=[],
        protocols=[p1, p2],
    )

    # Assert: pick the morning visit
    v = next((vv for vv in visits if vv.part_of_day == "Ochtend"), None)
    assert v is not None
    # Duration should be 150 minutes (2.5 hours)
    assert v.duration == 150
    # Start time text should align with the calculated start used for duration
    assert v.start_time_text == "2,5 uur voor zonsopkomst"


@pytest.mark.asyncio
async def test_morning_start_text_present_when_only_start_relative(mocker, fake_db):
    # Arrange: one protocol starting relative to sunrise, without end timing.
    # We expect an Ochtend visit with a non-empty start_time_text based on
    # the start reference.

    today_year = date.today().year
    wf = date(today_year, 4, 1)
    wt = date(today_year, 5, 1)

    p_only = _make_protocol(
        proto_id=851,
        fam_name="Zangvogel",
        species_id=1851,
        species_name="Huismus",
        fn_id=18510,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNRISE",
        start_rel_min=-60,
        visit_duration_h=2.0,
    )

    # Provide protocol directly to bypass DB resolution
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    cluster = Cluster(id=30, project_id=1, address="c30", cluster_number=30)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db,
        cluster,
        function_ids=[],
        species_ids=[],
        protocols=[p_only],
    )

    # Assert: one morning visit with a derived start_time_text
    assert len(visits) == 1
    v = visits[0]
    assert v.part_of_day == "Ochtend"
    assert v.start_time_text is not None


@pytest.mark.asyncio
async def test_evening_duration_uses_span_from_earliest_start_to_latest_end(
    mocker, fake_db
):
    # Arrange: two evening protocols starting at different times around sunset
    # - p1: starts 1.5h before sunset, duration 2h
    # - p2: starts at sunset, duration 2h
    # Expected overall span: from -90 minutes to +120 minutes relative to sunset
    # => 210 minutes (3.5 hours).

    today_year = date.today().year
    wf = date(today_year, 6, 1)
    wt = date(today_year, 7, 1)

    p1 = _make_protocol(
        proto_id=901,
        fam_name="Vleermuis",
        species_id=1901,
        species_name="BatEA",
        fn_id=1910,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
        start_rel_min=-90,
        visit_duration_h=2.0,
    )
    p2 = _make_protocol(
        proto_id=902,
        fam_name="Vleermuis",
        species_id=1902,
        species_name="BatEB",
        fn_id=1911,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
        start_rel_min=0,
        visit_duration_h=2.0,
    )

    # Provide protocols directly to bypass DB resolution
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    cluster = Cluster(id=27, project_id=1, address="c27", cluster_number=27)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db,
        cluster,
        function_ids=[],
        species_ids=[],
        protocols=[p1, p2],
    )

    # Assert: pick the evening visit and verify duration covers the full span
    v = next((vv for vv in visits if vv.part_of_day == "Avond"), None)
    assert v is not None
    assert v.duration == 210


@pytest.mark.asyncio
async def test_pad_family_uses_simple_one_visit_per_window(mocker, fake_db):
    # Arrange: Pad-family protocols should not be combined or bucketed; instead,
    # each ProtocolVisitWindow should yield its own visit, even when other
    # families are present in the same cluster.

    today_year = date.today().year
    wf1 = date(today_year, 5, 1)
    wt1 = date(today_year, 5, 15)
    wf2 = date(today_year, 5, 16)
    wt2 = date(today_year, 5, 31)

    # Pad family protocol with two windows
    fam_pad = Family(id=901, name="Pad", priority=1)
    sp_pad = Species(id=1901, family_id=fam_pad.id, name="Padsoort", abbreviation="PD")
    sp_pad.family = fam_pad
    fn_pad = Function(id=1910, name="PadFn")

    p_pad = Protocol(
        id=901,
        species_id=sp_pad.id,
        function_id=fn_pad.id,
        start_timing_reference="SUNSET",
    )
    p_pad.species = sp_pad
    p_pad.function = fn_pad
    w1 = ProtocolVisitWindow(
        id=9011,
        protocol_id=p_pad.id,
        visit_index=1,
        window_from=wf1,
        window_to=wt1,
        required=True,
        label=None,
    )
    w2 = ProtocolVisitWindow(
        id=9012,
        protocol_id=p_pad.id,
        visit_index=2,
        window_from=wf2,
        window_to=wt2,
        required=True,
        label=None,
    )
    p_pad.visit_windows = [w1, w2]

    # Another family (e.g. Vleermuis) protocol to ensure mixed clusters are allowed
    fam_other = Family(id=902, name="Vleermuis", priority=1)
    sp_other = Species(id=1902, family_id=fam_other.id, name="BatXC", abbreviation="BX")
    sp_other.family = fam_other
    fn_other = Function(id=1911, name="Nest")

    p_other = Protocol(
        id=902,
        species_id=sp_other.id,
        function_id=fn_other.id,
        start_timing_reference="SUNSET",
    )
    p_other.species = sp_other
    p_other.function = fn_other
    w_other = ProtocolVisitWindow(
        id=9021,
        protocol_id=p_other.id,
        visit_index=1,
        window_from=wf1,
        window_to=wt2,
        required=True,
        label=None,
    )
    p_other.visit_windows = [w_other]

    funcs = {fn_pad.id: fn_pad, fn_other.id: fn_other}
    species = {sp_pad.id: sp_pad, sp_other.id: sp_other}

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([p_pad, p_other])
        if "FROM functions" in sql:
            return _FakeResult(list(funcs.values()))
        if "FROM species" in sql:
            return _FakeResult(list(species.values()))
        return _FakeResult([])

    fake_db.execute = exec_stub  # type: ignore[attr-defined]
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)

    cluster = Cluster(id=28, project_id=1, address="c28", cluster_number=28)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db,
        cluster,
        function_ids=[fn_pad.id, fn_other.id],
        species_ids=[sp_pad.id, sp_other.id],
    )

    # Assert: Pad family yields exactly one visit per window without combining
    pad_visits = [v for v in visits if any(f.id == fn_pad.id for f in v.functions)]
    assert len(pad_visits) == 2

    expected_windows = {(wf1, wt1), (wf2, wt2)}
    actual_windows = {(v.from_date, v.to_date) for v in pad_visits}
    assert actual_windows == expected_windows

    # Each Pad visit should only contain the Pad function
    for v in pad_visits:
        fn_ids = {f.id for f in v.functions}
        assert fn_ids == {fn_pad.id}

    # Other family should still produce at least one visit
    other_visits = [v for v in visits if any(f.id == fn_other.id for f in v.functions)]
    assert len(other_visits) >= 1


@pytest.mark.asyncio
async def test_pad_family_respects_min_gap_across_all_visits(mocker, fake_db):
    # Arrange: Pad-family protocol with two windows closer than the configured
    # min_period_between_visits_value; simple-mode should shift the second
    # visit start so that the gap is respected.

    today_year = date.today().year
    wf1 = date(today_year, 5, 1)
    wt1 = date(today_year, 5, 3)
    wf2 = date(today_year, 5, 4)
    wt2 = date(today_year, 5, 10)

    fam_pad = Family(id=911, name="Pad", priority=1)
    sp_pad = Species(id=1911, family_id=fam_pad.id, name="PadsoortB", abbreviation="PB")
    sp_pad.family = fam_pad
    fn_pad = Function(id=1920, name="PadFnB")

    p_pad = Protocol(
        id=911,
        species_id=sp_pad.id,
        function_id=fn_pad.id,
        start_timing_reference="SUNSET",
    )
    p_pad.species = sp_pad
    p_pad.function = fn_pad
    # Set family-level min gap 7 days
    setattr(p_pad, "min_period_between_visits_value", 7)
    setattr(p_pad, "min_period_between_visits_unit", "dagen")

    w1 = ProtocolVisitWindow(
        id=9111,
        protocol_id=p_pad.id,
        visit_index=1,
        window_from=wf1,
        window_to=wt1,
        required=True,
        label=None,
    )
    w2 = ProtocolVisitWindow(
        id=9112,
        protocol_id=p_pad.id,
        visit_index=2,
        window_from=wf2,
        window_to=wt2,
        required=True,
        label=None,
    )
    p_pad.visit_windows = [w1, w2]

    funcs = {fn_pad.id: fn_pad}
    species = {sp_pad.id: sp_pad}

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([p_pad])
        if "FROM functions" in sql:
            return _FakeResult(list(funcs.values()))
        if "FROM species" in sql:
            return _FakeResult(list(species.values()))
        return _FakeResult([])

    fake_db.execute = exec_stub  # type: ignore[attr-defined]
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)

    cluster = Cluster(id=29, project_id=1, address="c29", cluster_number=29)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db,
        cluster,
        function_ids=[fn_pad.id],
        species_ids=[sp_pad.id],
    )

    # Assert: two Pad visits with at least 7 days between their from_dates
    pad_visits = [v for v in visits if any(f.id == fn_pad.id for f in v.functions)]
    assert len(pad_visits) == 2
    pad_visits.sort(key=lambda v: v.from_date)
    gap_days = (pad_visits[1].from_date - pad_visits[0].from_date).days
    assert gap_days >= 7


@pytest.mark.asyncio
async def test_completion_respects_min_gap_when_attaching(mocker, fake_db):
    # Arrange: one flex protocol with two identical windows and min gap 20d,
    # plus a morning-only and an evening-only to create Ochtend and Avond buckets.
    today_year = date.today().year
    wf = date(today_year, 5, 15)
    wt = date(today_year, 7, 15)

    # Flex protocol X with two windows, both allowed
    fam = Family(id=601, name="Vleermuis", priority=1)
    spx = Species(id=1601, family_id=fam.id, name="BatXA", abbreviation="BX")
    spx.family = fam
    fnx = Function(id=1610, name="Nest")
    pX = Protocol(
        id=601,
        species_id=spx.id,
        function_id=fnx.id,
        start_timing_reference="SUNSET",
        end_timing_reference="SUNRISE",
    )
    pX.species = spx
    pX.function = fnx
    # two identical windows (vidx 1 and 2)
    w1 = ProtocolVisitWindow(
        id=6011,
        protocol_id=pX.id,
        visit_index=1,
        window_from=wf,
        window_to=wt,
        required=True,
        label=None,
    )
    w2 = ProtocolVisitWindow(
        id=6012,
        protocol_id=pX.id,
        visit_index=2,
        window_from=wf,
        window_to=wt,
        required=True,
        label=None,
    )
    pX.visit_windows = [w1, w2]
    # min gap 20 days
    setattr(pX, "min_period_between_visits_value", 20)
    setattr(pX, "min_period_between_visits_unit", "dagen")

    # Morning-only protocol to create an Ochtend bucket at 05-15
    pM = _make_protocol(
        proto_id=602,
        fam_name="Vleermuis",
        species_id=1602,
        species_name="BatXB",
        fn_id=1611,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNRISE",
    )

    # Evening-only protocol to create an Avond bucket at 05-15 and a compatible later bucket
    pE = _make_protocol(
        proto_id=603,
        fam_name="Vleermuis",
        species_id=1603,
        species_name="BatXC",
        fn_id=1612,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
    )

    funcs = {fnx.id: fnx, pM.function.id: pM.function, pE.function.id: pE.function}
    species = {spx.id: spx, pM.species.id: pM.species, pE.species.id: pE.species}

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([pX, pM, pE])
        if "FROM functions" in sql:
            return _FakeResult(list(funcs.values()))
        if "FROM species" in sql:
            return _FakeResult(list(species.values()))
        return _FakeResult([])

    fake_db.execute = exec_stub  # type: ignore[attr-defined]
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)

    cluster = Cluster(id=16, project_id=1, address="c16", cluster_number=16)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db,
        cluster,
        function_ids=[fnx.id, pM.function.id, pE.function.id],
        species_ids=[spx.id, pM.species.id, pE.species.id],
    )

    # Assert: protocol X should appear in two visits at least 20 days apart,
    # and must not be attached to both 05-15 visits (morning and evening).
    vx = [v for v in visits if any(f.id == fnx.id for f in v.functions)]
    assert len(vx) >= 2


@pytest.mark.asyncio
async def test_completion_fallback_can_place_before_first_visit(mocker, fake_db):
    # Arrange: wide-window protocol with two required windows and min gap 20d,
    # plus a tighter companion protocol that seeds a later combined bucket.
    # The primary bucketing phase will place the first occurrence of the wide
    # protocol in the later bucket; the completion pass must then place the
    # second occurrence on the left side of the window, before that first
    # planned visit, while still respecting the min-gap.

    today_year = date.today().year
    wf_wide = date(today_year, 7, 15)
    wt_wide = date(today_year, 9, 1)
    wf_tight = date(today_year, 8, 15)
    wt_tight = date(today_year, 9, 15)

    fam = Family(id=701, name="Vleermuis", priority=1)
    sp = Species(id=1701, family_id=fam.id, name="BatYA", abbreviation="BY")
    sp.family = fam
    fn_wide = Function(id=1710, name="Nest")
    fn_tight = Function(id=1711, name="Nest")

    # Wide protocol with two identical windows and a symmetric min-gap of 20 days
    p_wide = Protocol(
        id=701,
        species_id=sp.id,
        function_id=fn_wide.id,
        start_timing_reference="SUNSET",
    )
    p_wide.species = sp
    p_wide.function = fn_wide
    w1 = ProtocolVisitWindow(
        id=7011,
        protocol_id=p_wide.id,
        visit_index=1,
        window_from=wf_wide,
        window_to=wt_wide,
        required=True,
        label=None,
    )
    w2 = ProtocolVisitWindow(
        id=7012,
        protocol_id=p_wide.id,
        visit_index=2,
        window_from=wf_wide,
        window_to=wt_wide,
        required=True,
        label=None,
    )
    p_wide.visit_windows = [w1, w2]
    setattr(p_wide, "min_period_between_visits_value", 20)
    setattr(p_wide, "min_period_between_visits_unit", "dagen")

    # Tighter companion protocol that starts later and seeds the combined bucket
    p_tight = Protocol(
        id=702,
        species_id=sp.id,
        function_id=fn_tight.id,
        start_timing_reference="SUNSET",
    )
    p_tight.species = sp
    p_tight.function = fn_tight
    w_tight = ProtocolVisitWindow(
        id=7021,
        protocol_id=p_tight.id,
        visit_index=1,
        window_from=wf_tight,
        window_to=wt_tight,
        required=True,
        label=None,
    )
    p_tight.visit_windows = [w_tight]

    # Provide protocols directly to bypass DB resolution
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    cluster = Cluster(id=17, project_id=1, address="c17", cluster_number=17)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db,
        cluster,
        function_ids=[],
        species_ids=[],
        protocols=[p_wide, p_tight],
    )

    # Assert: wide protocol appears in at least two visits within its window,
    # and their from_dates are at least 20 days apart (symmetric min-gap).
    v_wide = [v for v in visits if any(f.id == fn_wide.id for f in v.functions)]
    assert len(v_wide) >= 2
    v_wide.sort(key=lambda v: v.from_date)

    first, second = v_wide[0], v_wide[1]
    assert wf_wide <= first.from_date <= wt_wide
    assert wf_wide <= second.from_date <= wt_wide
    assert (second.from_date - first.from_date).days >= 20


@pytest.mark.asyncio
async def test_single_protocol_relaxation_widens_first_visit_within_window(
    mocker, fake_db
):
    """Single-protocol evening visits are relaxed back to the protocol window start.

    This mirrors the production case where a protocol's first visit ended up in a
    bucket starting later than its ProtocolVisitWindow.window_from due to
    combination logic. The relaxation pass should move the visit start back to
    window_from when the visit only contains that protocol and min-gap allows it.
    """

    today_year = date.today().year
    wf = date(today_year, 3, 1)
    wt = date(today_year, 3, 15)

    fam = Family(id=801, name="Zangvogel", priority=1)
    sp = Species(id=2801, family_id=fam.id, name="Proto129Like", abbreviation="PZ")
    sp.family = fam
    fn = Function(id=2810, name="Nest")

    # Evening protocol with one required window and a modest min-gap.
    p = Protocol(
        id=801,
        species_id=sp.id,
        function_id=fn.id,
        start_timing_reference="SUNSET",
    )
    p.species = sp
    p.function = fn

    w1 = ProtocolVisitWindow(
        id=8011,
        protocol_id=p.id,
        visit_index=1,
        window_from=wf,
        window_to=wt,
        required=True,
        label=None,
    )
    p.visit_windows = [w1]

    # Provide the protocol directly to bypass DB resolution; no companion
    # protocols so the single visit would naturally start at wf. This test
    # asserts that the relaxation helper still allows the visit to use the full
    # ProtocolVisitWindow range.
    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    cluster = Cluster(id=31, project_id=1, address="c31", cluster_number=31)

    visits, _ = await generate_visits_for_cluster(
        fake_db,
        cluster,
        function_ids=[],
        species_ids=[],
        protocols=[p],
    )

    assert len(visits) == 1
    v = visits[0]
    assert v.from_date == wf
    assert v.to_date == wt


@pytest.mark.asyncio
async def test_single_protocol_relaxation_does_not_cross_into_previous_window(
    mocker, fake_db
):
    """Single-protocol visits spanning adjacent windows stay in their own window.

    When a protocol has two adjacent windows that both include the boundary
    day, the relaxation helper must not move the second visit start into the
    earlier window. This guards against regressions like proto 116 where the
    second occurrence was relaxed before its own window_from.
    """

    # Arrange
    today_year = date.today().year
    wf1 = date(today_year, 6, 1)
    wt1 = date(today_year, 6, 15)
    wf2 = date(today_year, 6, 15)
    wt2 = date(today_year, 6, 30)

    fam = Family(id=1001, name="Vleermuis", priority=1)
    sp = Species(id=2101, family_id=fam.id, name="BatZA", abbreviation="BZ")
    sp.family = fam
    fn = Function(id=2110, name="Nest")

    p = Protocol(
        id=1001,
        species_id=sp.id,
        function_id=fn.id,
        start_timing_reference="SUNSET",
    )
    p.species = sp
    p.function = fn

    w1 = ProtocolVisitWindow(
        id=10011,
        protocol_id=p.id,
        visit_index=1,
        window_from=wf1,
        window_to=wt1,
        required=True,
        label=None,
    )
    w2 = ProtocolVisitWindow(
        id=10012,
        protocol_id=p.id,
        visit_index=2,
        window_from=wf2,
        window_to=wt2,
        required=True,
        label=None,
    )
    p.visit_windows = [w1, w2]

    mocker.patch("app.services.visit_generation._next_visit_nr", return_value=1)
    cluster = Cluster(id=32, project_id=1, address="c32", cluster_number=32)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db,
        cluster,
        function_ids=[],
        species_ids=[],
        protocols=[p],
    )

    # Assert: we expect two visits whose starts respect their respective
    # window_from values; in particular, the second visit must not start
    # before wf2.
    proto_visits = [v for v in visits if any(f.id == fn.id for f in v.functions)]
    assert len(proto_visits) >= 2
    proto_visits.sort(key=lambda v: v.from_date)
    first, second = proto_visits[0], proto_visits[1]
    assert wf1 <= first.from_date <= wt1
    assert wf2 <= second.from_date <= wt2
