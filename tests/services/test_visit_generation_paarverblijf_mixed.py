from datetime import date, time

from app.models.function import Function
from app.models.protocol import Protocol
from app.models.species import Species
from app.services.visit_generation_common import calculate_visit_props

# Visit 1 anchors mid-August (sunset estimate 20:45); visit 2 lands in
# September (sunset estimate 20:00) via the per-visit reference date.
REF_DATE = date(2025, 8, 20)
REF_DATE_SEPT = date(2025, 9, 5)


def _protocol(
    proto_id,
    species_abbr,
    *,
    start_ref,
    rel_minutes=None,
    absolute_from=None,
    duration_hours=2.0,
    function_name="Paarverblijf",
):
    p = Protocol(
        id=proto_id,
        start_timing_reference=start_ref,
        start_time_relative_minutes=rel_minutes,
        start_time_absolute_from=absolute_from,
        visit_duration_hours=duration_hours,
    )
    p.function = Function(id=proto_id * 100, name=function_name)
    p.species = Species(id=proto_id * 10, name=species_abbr, abbreviation=species_abbr)
    return p


def test_mv_plus_absolute_2200_august_visit_span_is_195():
    # August sunset 20:45; MV runs to 23:45, absolute 22:00 protocol to 00:00.
    # Span = 20:45 -> 00:00 = 195 min (3h15).
    mv = _protocol(1, "MV", start_ref="SUNSET", rel_minutes=0, duration_hours=3.0)
    wv = _protocol(2, "WV", start_ref="ABSOLUTE_TIME", absolute_from=time(22, 0))

    duration, text, remark = calculate_visit_props(
        [mv, wv], "Avond", reference_date=REF_DATE
    )

    assert duration == 195
    assert text == "Zonsondergang"
    assert remark == (
        "Onderzoek doen tot minimaal 00:00; opgegeven tijdsduur is een indicatie."
    )


def test_mv_plus_absolute_2200_september_visit_span_is_240():
    # September sunset 20:00; absolute 22:00 protocol runs to 00:00.
    # Span = 20:00 -> 00:00 = 240 min (4h).
    mv = _protocol(1, "MV", start_ref="SUNSET", rel_minutes=0, duration_hours=3.0)
    wv = _protocol(2, "WV", start_ref="ABSOLUTE_TIME", absolute_from=time(22, 0))

    duration, text, remark = calculate_visit_props(
        [mv, wv], "Avond", reference_date=REF_DATE_SEPT
    )

    assert duration == 240
    assert text == "Zonsondergang"
    assert remark == (
        "Onderzoek doen tot minimaal 00:00; opgegeven tijdsduur is een indicatie."
    )


def test_mv_plus_rd_visit1_reinterprets_rd_as_2215_and_remarks_until_0015():
    mv = _protocol(1, "MV", start_ref="SUNSET", rel_minutes=0, duration_hours=3.0)
    # RD Paarverblijf visit 1 is forced to ABSOLUTE 23:00 by _get_effective_timing.
    rd = _protocol(2, "RD", start_ref="SUNSET", rel_minutes=60)

    duration, text, remark = calculate_visit_props(
        [mv, rd], "Avond", reference_date=REF_DATE, visit_indices={rd.id: 1}
    )

    # August sunset 20:45; MV +3h -> 23:45; RD 22:15 +2h -> 00:15. Span = 210 (3h30).
    assert duration == 210
    assert text == "Zonsondergang"
    assert remark == (
        "Onderzoek doen tot minimaal 00:15; opgegeven tijdsduur is een indicatie."
    )


def test_gd_plus_rd_visit1_keeps_plain_absolute_2300_no_remark():
    # No MV protocol -> not a sunset-dependent mix. RD visit 1 keeps its plain
    # absolute 23:00-01:00 timing; adding GD must not change it or add a remark.
    gd = _protocol(1, "GD", start_ref="SUNSET", rel_minutes=60)
    rd = _protocol(2, "RD", start_ref="SUNSET", rel_minutes=60)

    duration, text, remark = calculate_visit_props(
        [gd, rd], "Avond", reference_date=REF_DATE, visit_indices={rd.id: 1}
    )

    assert duration == 120
    assert text == "23:00"
    assert remark is None


def test_standalone_rd_visit1_is_unchanged_2300_no_remark():
    rd = _protocol(1, "RD", start_ref="SUNSET", rel_minutes=60)

    duration, text, remark = calculate_visit_props(
        [rd], "Avond", reference_date=REF_DATE, visit_indices={rd.id: 1}
    )

    assert duration == 120
    assert text == "23:00"
    assert remark is None


def test_mv_only_is_unchanged_no_remark():
    mv = _protocol(1, "MV", start_ref="SUNSET", rel_minutes=0, duration_hours=3.0)

    duration, text, remark = calculate_visit_props(
        [mv], "Avond", reference_date=REF_DATE
    )

    assert duration == 180
    assert text == "Zonsondergang"
    assert remark is None


def test_span_survives_a_protocol_without_an_evening_start():
    # A protocol with a non-evening reference (e.g. SUNRISE) bundled into an
    # evening visit must not abort the span calc and fall back to max duration.
    mv = _protocol(1, "MV", start_ref="SUNSET", rel_minutes=0, duration_hours=3.0)
    rd = _protocol(2, "RD", start_ref="SUNSET", rel_minutes=60)
    other = _protocol(
        3, "XX", start_ref="SUNRISE", rel_minutes=0, function_name="Vliegroute"
    )

    duration, text, remark = calculate_visit_props(
        [mv, rd, other],
        "Avond",
        reference_date=REF_DATE,
        visit_indices={rd.id: 1, mv.id: 1, other.id: 1},
    )

    assert duration == 210  # not 180 (= MV's bare 3h fallback)
    assert text == "Zonsondergang"
    assert remark == (
        "Onderzoek doen tot minimaal 00:15; opgegeven tijdsduur is een indicatie."
    )


def test_massawinter_plus_mv_paarverblijf_does_not_shorten_span():
    # Adding a Massawinterverblijfplaats protocol to an MV Paarverblijf evening
    # visit must not collapse the duration to max(single protocol) = 180. The
    # 00:00 massawinter anchor is subsumed by the sunset->00:15 paarverblijf work.
    mw = _protocol(
        1,
        "GD",
        start_ref="ABSOLUTE_TIME",
        absolute_from=time(0, 0),
        function_name="Massawinterverblijfplaats",
    )
    mv = _protocol(2, "MV", start_ref="SUNSET", rel_minutes=0, duration_hours=3.0)
    rd = _protocol(3, "RD", start_ref="SUNSET", rel_minutes=60)
    wv = _protocol(4, "WV", start_ref="ABSOLUTE_TIME", absolute_from=time(22, 0))

    with_mw = calculate_visit_props(
        [mw, mv, rd, wv],
        "Avond",
        reference_date=REF_DATE,
        visit_indices={p.id: 1 for p in (mw, mv, rd, wv)},
    )
    without_mw = calculate_visit_props(
        [mv, rd, wv],
        "Avond",
        reference_date=REF_DATE,
        visit_indices={p.id: 1 for p in (mv, rd, wv)},
    )

    assert with_mw[0] == 210
    assert with_mw == without_mw


def test_pure_sunset_combo_has_no_remark():
    gd = _protocol(1, "GD", start_ref="SUNSET", rel_minutes=60)
    kd = _protocol(2, "KD", start_ref="SUNSET", rel_minutes=0)

    _duration, _text, remark = calculate_visit_props(
        [gd, kd], "Avond", reference_date=REF_DATE
    )

    assert remark is None
