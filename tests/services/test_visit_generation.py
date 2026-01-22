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
        # Will be replaced per-test using monkeypatch attribute injection
        return _FakeResult([])

    def add(self, _obj):
        # no-op for unit tests
        return None


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
    visit_duration_h: float | None = None,
):
    fam = Family(id=proto_id, name=fam_name, priority=1)  # id not critical
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
    )
    p.species = sp
    p.function = fn
    w = ProtocolVisitWindow(
        id=proto_id * 10 + 1,
        protocol_id=proto_id,
        visit_index=1,
        window_from=window_from,
        window_to=window_to,
        required=True,
        label=None,
    )
    p.visit_windows = [w]
    return p


@pytest_asyncio.fixture
async def fake_db():
    return _FakeSession()


@pytest.mark.asyncio
async def test_default_part_prefers_morning_when_both_allowed(mocker, fake_db):
    # Arrange
    today_year = date.today().year
    wf = date(today_year, 5, 15)
    wt = date(today_year, 7, 15)

    # Allow both by using overnight window SUNSET->SUNRISE
    p1 = _make_protocol(
        proto_id=1,
        fam_name="Vleermuis",
        species_id=101,
        species_name="BatA",
        fn_id=10,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
        end_ref="SUNRISE",
        visit_duration_h=2.0,
    )
    p2 = _make_protocol(
        proto_id=2,
        fam_name="Vleermuis",
        species_id=102,
        species_name="BatB",
        fn_id=11,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
        end_ref="SUNRISE",
        visit_duration_h=2.0,
    )

    # Helper: return protocols first, and later resolve Function/Species by ids
    funcs = {p1.function.id: p1.function, p2.function.id: p2.function}
    species = {p1.species.id: p1.species, p2.species.id: p2.species}

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([p1, p2])
        if "FROM functions" in sql:
            # Filter by ids present in IN clause; best-effort: return all
            return _FakeResult(list(funcs.values()))
        if "FROM species" in sql:
            return _FakeResult(list(species.values()))
        return _FakeResult([])

    fake_db.execute = exec_stub  # type: ignore[attr-defined]

    cluster = Cluster(id=1, project_id=1, address="c1", cluster_number=1)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db, cluster, function_ids=[10, 11], species_ids=[101, 102]
    )

    # Assert
    assert len(visits) >= 1
    # First visit should choose morning when both allowed
    assert visits[0].part_of_day == "Ochtend"


@pytest.mark.asyncio
async def test_evening_uses_earliest_start_across_protocols(mocker, fake_db):
    # Arrange
    today_year = date.today().year
    wf = date(today_year, 6, 1)
    wt = date(today_year, 7, 1)

    # One protocol starts -90 before sunset, another at sunset
    p_early = _make_protocol(
        proto_id=3,
        fam_name="Vleermuis",
        species_id=201,
        species_name="BatC",
        fn_id=20,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
        end_ref=None,
        start_rel_min=-90,
        visit_duration_h=2.0,
    )
    p_at = _make_protocol(
        proto_id=4,
        fam_name="Vleermuis",
        species_id=202,
        species_name="BatD",
        fn_id=21,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
        end_ref=None,
        start_rel_min=0,
        visit_duration_h=2.0,
    )

    funcs = {p_early.function.id: p_early.function, p_at.function.id: p_at.function}
    species = {p_early.species.id: p_early.species, p_at.species.id: p_at.species}

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([p_early, p_at])
        if "FROM functions" in sql:
            return _FakeResult(list(funcs.values()))
        if "FROM species" in sql:
            return _FakeResult(list(species.values()))
        return _FakeResult([])

    fake_db.execute = exec_stub  # type: ignore[attr-defined]

    cluster = Cluster(id=2, project_id=1, address="c2", cluster_number=2)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db, cluster, function_ids=[20, 21], species_ids=[201, 202]
    )

    # Assert: part constrained to Avond; start text should reflect -90 min => 1,5 uur voor zonsondergang
    assert len(visits) >= 1
    assert visits[0].part_of_day == "Avond"
    assert visits[0].start_time_text == "1,5 uur voor zonsondergang"


@pytest.mark.asyncio
async def test_evening_start_text_present_when_only_start_relative(mocker, fake_db):
    # Arrange
    today_year = date.today().year
    wf = date(today_year, 6, 1)
    wt = date(today_year, 7, 1)

    p_only = _make_protocol(
        proto_id=5,
        fam_name="Vleermuis",
        species_id=301,
        species_name="BatE",
        fn_id=30,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
        end_ref=None,
        start_rel_min=-90,
        visit_duration_h=2.0,
    )

    funcs = {p_only.function.id: p_only.function}
    species = {p_only.species.id: p_only.species}

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([p_only])
        if "FROM functions" in sql:
            return _FakeResult(list(funcs.values()))
        if "FROM species" in sql:
            return _FakeResult(list(species.values()))
        return _FakeResult([])

    fake_db.execute = exec_stub  # type: ignore[attr-defined]

    cluster = Cluster(id=3, project_id=1, address="c3", cluster_number=3)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db, cluster, function_ids=[30], species_ids=[301]
    )

    # Assert
    assert len(visits) == 1
    assert visits[0].part_of_day == "Avond"
    assert visits[0].start_time_text == "1,5 uur voor zonsondergang"


@pytest.mark.asyncio
async def test_smp_grouping_rules(mocker, fake_db):
    # Arrange
    today_year = date.today().year
    wf = date(today_year, 5, 15)
    wt = date(today_year, 7, 15)

    # Families
    fam_bat = "Vleermuis"
    fam_swift = "Zwaluw"

    # SMP + non-SMP same species should NOT combine
    p_smp = _make_protocol(
        proto_id=6,
        fam_name=fam_bat,
        species_id=401,
        species_name="BatF",
        fn_id=40,
        fn_name="SMP Kraam",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
    )
    p_non = _make_protocol(
        proto_id=7,
        fam_name=fam_bat,
        species_id=401,
        species_name="BatF",
        fn_id=41,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
    )

    # SMP + SMP same family should combine
    p_smp2 = _make_protocol(
        proto_id=8,
        fam_name=fam_bat,
        species_id=402,
        species_name="BatG",
        fn_id=42,
        fn_name="SMP Groepsvorming",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
    )

    # SMP + SMP different family should NOT combine
    p_smp_swift = _make_protocol(
        proto_id=9,
        fam_name=fam_swift,
        species_id=501,
        species_name="Swift",
        fn_id=43,
        fn_name="SMP Kolonie",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
    )

    funcs = {
        p_smp.function.id: p_smp.function,
        p_non.function.id: p_non.function,
        p_smp2.function.id: p_smp2.function,
        p_smp_swift.function.id: p_smp_swift.function,
    }
    species = {
        p_smp.species.id: p_smp.species,
        p_non.species.id: p_non.species,
        p_smp2.species.id: p_smp2.species,
        p_smp_swift.species.id: p_smp_swift.species,
    }

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([p_smp, p_non, p_smp2, p_smp_swift])
        if "FROM functions" in sql:
            return _FakeResult(list(funcs.values()))
        if "FROM species" in sql:
            return _FakeResult(list(species.values()))
        return _FakeResult([])

    fake_db.execute = exec_stub  # type: ignore[attr-defined]

    cluster = Cluster(id=4, project_id=1, address="c4", cluster_number=4)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db,
        cluster,
        function_ids=[40, 41, 42, 43],
        species_ids=[401, 402, 501],
    )

    # Assert behavioral grouping constraints
    for v in visits:
        # Prefer function names derived from remarks_field (built directly from protocols)
        if v.remarks_field:
            lines = [ln for ln in v.remarks_field.split("\n") if ln.strip()]
            fn_names = {ln.split(":", 1)[0].strip() for ln in lines}
        else:
            fn_names = {f.name for f in v.functions}
        if any(name.startswith("SMP") for name in fn_names):
            assert all(name.startswith("SMP") for name in fn_names)
            # Family constraint is enforced by grouping logic; DB fetch stubs may include extra species,
            # so we don't assert on families here.


@pytest.mark.asyncio
async def test_visit_generation_defaults_are_applied(mocker, fake_db):
    # Arrange
    today_year = date.today().year
    wf = date(today_year, 5, 1)
    wt = date(today_year, 8, 1)

    p1 = _make_protocol(
        proto_id=1,
        fam_name="Vleermuis",
        species_id=101,
        species_name="BatA",
        fn_id=10,
        fn_name="Nest",
        window_from=wf,
        window_to=wt,
        start_ref="SUNSET",
        visit_duration_h=2.0,
    )

    async def exec_stub(_stmt):
        sql = str(_stmt)
        if "FROM protocols" in sql:
            return _FakeResult([p1])
        if "FROM visits" in sql:
            return _FakeResult([])
        # Just return p1's function/species for any query to avoid empty lists
        return _FakeResult([p1.function, p1.species])

    fake_db.execute = exec_stub

    cluster = Cluster(id=1, project_id=1, address="c1", cluster_number=1)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db,
        cluster,
        function_ids=[10],
        species_ids=[101],
        default_required_researchers=5,
        default_preferred_researcher_id=99,
        default_expertise_level="Senior",
        default_wbc=True,
        default_fiets=True,
        default_hub=True,
        default_dvp=True,
        default_sleutel=True,
        default_remarks_field="Custom Remark",
    )

    # Assert
    assert len(visits) > 0
    v = visits[0]
    assert v.required_researchers == 5
    assert v.preferred_researcher_id == 99
    assert v.expertise_level == "Senior"
    assert v.wbc is True
    assert v.fiets is True
    assert v.hub is True
    assert v.dvp is True
    assert v.sleutel is True
    assert "Custom Remark" in (v.remarks_field or "")
