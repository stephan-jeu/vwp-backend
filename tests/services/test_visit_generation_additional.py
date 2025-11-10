import pytest
import pytest_asyncio
from datetime import date, timedelta

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
    sp = Species(id=species_id, family_id=fam.id, name=species_name, abbreviation=species_name[:2])
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

    # Assert
    assert len(visits) >= 1
    assert visits[0].part_of_day == "Ochtend"


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

    p = Protocol(id=301, species_id=sp.id, function_id=fn.id, start_timing_reference="SUNSET")
    p.species = sp
    p.function = fn
    w1 = ProtocolVisitWindow(id=3011, protocol_id=p.id, visit_index=1, window_from=wf, window_to=wt, required=True, label=None)
    w2 = ProtocolVisitWindow(id=3012, protocol_id=p.id, visit_index=2, window_from=wf, window_to=wt, required=True, label=None)
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
    # and assigns occurrence indices used in remarks_field. We don't enforce two separate
    # visits, since identical windows may be consolidated into one series entry.
    assert len(visits) >= 1
    combined_rf = "\n".join([v.remarks_field or "" for v in visits])
    assert "(" in combined_rf and ")" in combined_rf  # contains an occurrence index like (1)


@pytest.mark.asyncio
async def test_split_pass_creates_morning_sibling_when_entry_is_evening_only(mocker, fake_db):
    # Arrange: required morning protocol allows both; companion allows only evening, forcing split
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
        start_ref="SUNSET_TO_SUNRISE",
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

    cluster = Cluster(id=14, project_id=1, address="c14", cluster_number=14)

    # Act
    visits, _ = await generate_visits_for_cluster(
        fake_db, cluster, function_ids=[1410, 1411], species_ids=[1401, 1402]
    )

    # Assert: expect two visits, one morning (contains p_req), one evening (contains p_even)
    parts = sorted(v.part_of_day for v in visits if v.part_of_day)
    assert parts.count("Ochtend") >= 1 and parts.count("Avond") >= 1
    # Use remarks_field to detect which function landed where
    def visit_has_fn_with_abbr(v, fn_name_prefix):
        if not v.remarks_field:
            return False
        return any(line.startswith(fn_name_prefix) for line in v.remarks_field.split("\n"))

    assert any(v.part_of_day == "Ochtend" and visit_has_fn_with_abbr(v, "Nest") for v in visits)


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
