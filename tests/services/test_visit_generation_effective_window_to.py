from datetime import date

from app.models.family import Family
from app.models.function import Function
from app.models.protocol import Protocol
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.models.species import Species
from app.services.visit_generation_common import _generate_visit_requests


def _make_protocol(pid: int, windows: list[tuple[date, date]], gap_days: int) -> Protocol:
    fam = Family(id=pid, name="Fam", priority=1)
    sp = Species(id=pid, family_id=fam.id, name="Sp", abbreviation="SP")
    sp.family = fam
    fn = Function(id=pid, name="Fn")

    p = Protocol(
        id=pid,
        species_id=sp.id,
        function_id=fn.id,
        start_timing_reference="SUNSET",
    )
    p.species = sp
    p.function = fn
    p.min_period_between_visits_value = gap_days
    p.min_period_between_visits_unit = "dagen"
    p.visit_windows = [
        ProtocolVisitWindow(
            id=pid * 10 + i + 1,
            protocol_id=pid,
            visit_index=i + 1,
            window_from=wf,
            window_to=wt,
            required=True,
            label=None,
        )
        for i, (wf, wt) in enumerate(windows)
    ]
    return p


def test_effective_window_to_shrinks_shared_window_for_predecessor():
    # Both visits share the same 15 mei - 15 jul window; a 20-day gap means
    # visit 1's *reported* deadline should move up so visit 2 still fits.
    y = date.today().year
    shared = (date(y, 5, 15), date(y, 7, 15))
    p = _make_protocol(1, [shared, shared], gap_days=20)

    reqs = _generate_visit_requests([p])
    v1, v2 = sorted(reqs, key=lambda r: r.visit_index)

    assert v1.effective_window_to == date(y, 6, 25)
    assert v2.effective_window_to == date(y, 7, 15)


def test_effective_window_to_unchanged_for_already_sequential_windows():
    # Visit 1 must be done by 15 juni regardless of the gap, because visit 2's
    # own window doesn't open until 15 juni anyway. The gap-derived limit
    # (30 juni - 10d = 20 juni) is looser than the explicit window and must
    # not push the deadline out to 20 juni.
    y = date.today().year
    p = _make_protocol(
        2,
        [(date(y, 6, 1), date(y, 6, 15)), (date(y, 6, 15), date(y, 6, 30))],
        gap_days=10,
    )

    reqs = _generate_visit_requests([p])
    v1, v2 = sorted(reqs, key=lambda r: r.visit_index)

    assert v1.effective_window_to == date(y, 6, 15)
    assert v2.effective_window_to == date(y, 6, 30)


def test_effective_window_to_propagates_through_chain_of_three():
    y = date.today().year
    shared = (date(y, 4, 1), date(y, 8, 1))
    p = _make_protocol(3, [shared, shared, shared], gap_days=15)

    reqs = _generate_visit_requests([p])
    v1, v2, v3 = sorted(reqs, key=lambda r: r.visit_index)

    assert v3.effective_window_to == date(y, 8, 1)
    assert v2.effective_window_to == date(y, 7, 17)
    assert v1.effective_window_to == date(y, 7, 2)


def test_effective_window_to_never_drops_below_effective_window_from():
    # Windows tight enough that the gap-derived deadline would fall before
    # the predecessor's own (forward-shifted) earliest start; the reported
    # to_date must not become inverted/empty.
    y = date.today().year
    p = _make_protocol(
        4,
        [(date(y, 5, 1), date(y, 5, 5)), (date(y, 5, 1), date(y, 5, 5))],
        gap_days=20,
    )

    reqs = _generate_visit_requests([p])
    v1, v2 = sorted(reqs, key=lambda r: r.visit_index)

    assert v1.effective_window_to >= v1.effective_window_from
