import pytest
from datetime import date

from app.models.family import Family
from app.models.species import Species
from app.models.function import Function
from app.models.protocol import Protocol
from app.models.protocol_visit_window import ProtocolVisitWindow
from app.services.visit_generation import _relax_single_protocol_visit_starts


def _make_proto_with_window(proto_id: int, wf: date, wt: date) -> Protocol:
    fam = Family(id=proto_id, name="Fam", priority=1)
    sp = Species(
        id=proto_id * 10, family_id=fam.id, name=f"Sp{proto_id}", abbreviation="SP"
    )
    sp.family = fam
    fn = Function(id=proto_id * 100, name="Fn")

    p = Protocol(
        id=proto_id,
        species_id=sp.id,
        function_id=fn.id,
        start_timing_reference="SUNSET",
    )
    p.species = sp
    p.function = fn
    w = ProtocolVisitWindow(
        id=proto_id * 1000 + 1,
        protocol_id=p.id,
        visit_index=1,
        window_from=wf,
        window_to=wt,
        required=True,
        label=None,
    )
    p.visit_windows = [w]
    return p


@pytest.mark.asyncio
async def test_multi_protocol_relaxation_moves_shared_visit_left_within_shared_window():
    """A combined multi-protocol visit can be relaxed earlier within shared windows.

    Two protocols share the same visit window; a multi-protocol visit that starts
    later inside that window should be relaxed back to the window_from, while
    staying within the window and without violating any min-gap (here zero).
    """

    today_year = date.today().year
    wf = date(today_year, 5, 15)
    wt = date(today_year, 6, 15)

    p1 = _make_proto_with_window(2001, wf, wt)
    p2 = _make_proto_with_window(2002, wf, wt)

    # visits_to_create uses the same shape as generate_visits_for_cluster's
    # intermediate representation.
    visits_to_create = [
        {
            "from_date": date(today_year, 6, 1),
            "to_date": wt,
            "protocols": [p1, p2],
            "chosen_part_of_day": "Avond",
            "proto_parts": {p1.id: None, p2.id: None},
            "proto_pvw_ids": {
                p1.id: p1.visit_windows[0].id,
                p2.id: p2.visit_windows[0].id,
            },
        }
    ]

    # proto_windows mirrors the structure built in generate_visits_for_cluster
    proto_windows = {
        p1.id: [(1, wf, wt, None, p1.visit_windows[0].id)],
        p2.id: [(1, wf, wt, None, p2.visit_windows[0].id)],
    }
    proto_id_to_protocol = {p1.id: p1, p2.id: p2}

    _relax_single_protocol_visit_starts(
        visits_to_create=visits_to_create,
        proto_windows=proto_windows,
        proto_id_to_protocol=proto_id_to_protocol,
    )

    assert len(visits_to_create) == 1
    entry = visits_to_create[0]
    assert entry["from_date"] == wf
    assert entry["to_date"] == wt
