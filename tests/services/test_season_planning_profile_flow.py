from datetime import date
from types import SimpleNamespace

import pytest

from app.services.season_planning_service import (
    SeasonPlanningService,
    _build_capacity_profiles,
    _bottleneck_analysis,
    _profile_max_flow,
)
from core.settings import get_settings

# ISO week 20 of 2026: Monday 11 May - Friday 15 May
WEEK = 20
START = date(2026, 5, 11)

_USER_FLAGS = (
    "vleermuis",
    "smp_vleermuis",
    "smp_gierzwaluw",
    "smp_huismus",
    "vrfg",
    "langoor",
    "schijfhoren",
    "zwaluw",
    "vlinder",
    "teunisbloempijlstaart",
    "zangvogel",
    "roofvogel",
    "pad",
    "biggenkruid",
)


def make_user(uid: int, *flags: str) -> SimpleNamespace:
    u = SimpleNamespace(
        id=uid, contract_type="intern", experience_bat="medior", deleted_at=None
    )
    for flag in _USER_FLAGS:
        setattr(u, flag, flag in flags)
    return u


def make_visit(vid: int, family: str, *, smp: bool = False, part="Avond"):
    proto = SimpleNamespace(
        id=vid,
        min_period_between_visits_value=0,
        min_period_between_visits_unit="days",
        start_timing_reference=None,
        requires_june_visit=False,
    )
    pvw = SimpleNamespace(
        protocol=proto,
        protocol_id=vid,
        visit_index=1,
        window_from=START,
        window_to=date(2026, 5, 15),
    )
    return SimpleNamespace(
        id=vid,
        cluster_id=vid,
        cluster=SimpleNamespace(project_id=vid),
        sleutel=False,
        vog=False,
        priority=False,
        from_date=START,
        to_date=date(2026, 5, 15),
        planned_week=None,
        provisional_week=None,
        provisional_locked=False,
        custom_function_name=None,
        custom_species_name=None,
        required_researchers=1,
        researchers=[],
        part_of_day=part,
        functions=[SimpleNamespace(name="SMP Kraamverblijf" if smp else "Kraamverblijf")],
        species=[SimpleNamespace(family=SimpleNamespace(name=family))],
        protocol_visit_windows=[pvw],
    )


def night_availability(user_ids, nights=1, flex=0):
    return {
        (uid, WEEK): SimpleNamespace(
            morning_days=0, daytime_days=0, nighttime_days=nights, flex_days=flex
        )
        for uid in user_ids
    }


@pytest.fixture
def profile_flow(monkeypatch):
    def _set(enabled: bool):
        monkeypatch.setattr(get_settings(), "constraint_profile_flow", enabled)

    return _set


def _unscheduled(diagnostics) -> set[int]:
    return {
        d.visit_id for d in diagnostics if d.action == "planning_season_unscheduled"
    }


def _anna_bram_cees():
    users = [
        make_user(1, "vleermuis"),  # Anna
        make_user(2, "vleermuis", "smp_vleermuis"),  # Bram
        make_user(3, "roofvogel"),  # Cees
    ]
    visits = [
        make_visit(101, "Vleermuis"),
        make_visit(102, "Vleermuis"),
        make_visit(103, "Vleermuis", smp=True),
    ]
    return users, visits, night_availability([1, 2, 3])


def test_skill_pools_overcount_multi_skilled_researcher(profile_flow):
    """Documents the old behaviour: Bram is counted in both pools."""
    profile_flow(False)
    users, visits, avail = _anna_bram_cees()

    diagnostics = SeasonPlanningService.solve_season(
        START, visits, users, avail, num_workers=1
    )

    assert _unscheduled(diagnostics) == set()


def test_profile_flow_counts_researcher_once(profile_flow):
    profile_flow(True)
    users, visits, avail = _anna_bram_cees()

    diagnostics = SeasonPlanningService.solve_season(
        START, visits, users, avail, num_workers=1
    )

    assert len(_unscheduled(diagnostics)) == 1


def test_profile_flow_uses_flex_for_any_daypart(profile_flow):
    profile_flow(True)
    users = [make_user(1, "vleermuis")]
    visits = [make_visit(101, "Vleermuis"), make_visit(102, "Vleermuis", part=None)]
    avail = night_availability([1], nights=0, flex=2)

    diagnostics = SeasonPlanningService.solve_season(
        START, visits, users, avail, num_workers=1
    )

    assert _unscheduled(diagnostics) == set()
    assert all(v.provisional_week == WEEK for v in visits)


def test_profile_flow_flex_is_not_double_counted(profile_flow):
    profile_flow(True)
    users = [make_user(1, "vleermuis")]
    visits = [
        make_visit(101, "Vleermuis", part="Ochtend"),
        make_visit(102, "Vleermuis", part="Avond"),
    ]
    avail = night_availability([1], nights=0, flex=1)

    diagnostics = SeasonPlanningService.solve_season(
        START, visits, users, avail, num_workers=1
    )

    assert len(_unscheduled(diagnostics)) == 1


def test_profile_max_flow_reports_unmet_and_remaining():
    users = [SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)]
    skills = {1: {"Vleermuis"}, 2: {"Vleermuis", "SMP Vleermuis"}, 3: {"Roofvogel"}}
    profiles = _build_capacity_profiles(users, night_availability([1, 2, 3]), skills, [WEEK])

    result = _profile_max_flow(
        profiles, WEEK, {("Vleermuis", "n"): 2, ("SMP Vleermuis", "n"): 1}
    )

    assert sum(result.unmet.values()) == 1
    by_skills = {p.skills: result.remaining[p.id] for p in profiles}
    # Only Cees has a night left
    assert by_skills[frozenset({"Roofvogel"})] == (0, 0, 1, 0)
    assert by_skills[frozenset({"Vleermuis"})] == (0, 0, 0, 0)


def test_profile_max_flow_any_skill_uses_every_profile():
    users = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    skills = {1: {"Vleermuis"}, 2: set()}
    profiles = _build_capacity_profiles(users, night_availability([1, 2]), skills, [WEEK])

    result = _profile_max_flow(profiles, WEEK, {("*", "a"): 2, ("Vleermuis", "n"): 1})

    assert sum(result.unmet.values()) == 1


def test_capacity_grid_spare_excludes_researchers_used_elsewhere(profile_flow):
    profile_flow(True)
    users, visits, avail = _anna_bram_cees()
    users.append(make_user(4, "smp_vleermuis"))  # Dirk: SMP only, idle at night
    avail.update(night_availability([4]))
    for v in visits:
        v.provisional_week = WEEK

    result = SeasonPlanningService._build_capacity_grid(START, visits, users, avail)

    rows = result.week_view.rows
    week_iso = f"2026-W{WEEK:02d}"
    bat = rows["Vleermuis - Avond"][week_iso]
    smp = rows["SMP Vleermuis - Avond"][week_iso]
    # Dirk takes the SMP visit, so Anna and Bram cover both bat visits.
    assert (bat.planned, bat.spare, bat.shortage) == (2, 0, 0)
    # Dirk's night is used; Bram (the other SMP researcher) is busy with bats.
    assert (smp.planned, smp.spare, smp.shortage) == (1, 0, 0)


def _week_visit(vid: int, first: date, last: date, family="Vleermuis"):
    v = make_visit(vid, family)
    v.from_date, v.to_date = first, last
    v.protocol_visit_windows[0].window_from = first
    v.protocol_visit_windows[0].window_to = last
    return v


def _nights_per_week(user_id: int, weeks: range, nights: int = 1) -> dict:
    return {
        (user_id, w): SimpleNamespace(
            morning_days=0, daytime_days=0, nighttime_days=nights, flex_days=0
        )
        for w in weeks
    }


def test_bottleneck_only_where_demand_cannot_move():
    """2 visits only fit in week 20, 10 visits may go anywhere in weeks 20-30."""
    users = [make_user(1, "vleermuis")]
    avail = _nights_per_week(1, range(20, 31))
    fixed = [_week_visit(i, date(2026, 5, 11), date(2026, 5, 15)) for i in (1, 2)]
    flexible = [
        _week_visit(i, date(2026, 5, 11), date(2026, 7, 24)) for i in range(3, 13)
    ]

    report = _bottleneck_analysis(START, fixed + flexible, users, avail)

    # 12 nights of demand, 11 nights of capacity. Weeks 21-30 are full too, but
    # an extra night there does not help: only week 20 is a real bottleneck.
    assert report.total_unmet_days == 1
    assert report.week_skills == {"2026-W20": ["Vleermuis"]}
    assert [(p.from_week, p.to_week, p.unmet_days) for p in report.periods] == [
        ("2026-W20", "2026-W20", 1)
    ]


def test_bottleneck_period_spans_shared_window():
    """7 visits share weeks 20-23 with 4 nights: extra capacity helps in each week."""
    users = [make_user(1, "vleermuis")]
    avail = _nights_per_week(1, range(20, 31))
    visits = [
        _week_visit(i, date(2026, 5, 11), date(2026, 6, 5)) for i in range(1, 8)
    ]

    report = _bottleneck_analysis(START, visits, users, avail)

    assert report.total_unmet_days == 3
    assert [(p.from_week, p.to_week, p.unmet_days) for p in report.periods] == [
        ("2026-W20", "2026-W23", 3)
    ]


def test_bottleneck_empty_when_everything_fits():
    users = [make_user(1, "vleermuis")]
    avail = _nights_per_week(1, range(20, 31))
    visits = [
        _week_visit(i, date(2026, 5, 11), date(2026, 7, 24)) for i in range(1, 6)
    ]

    report = _bottleneck_analysis(START, visits, users, avail)

    assert report.total_unmet_days == 0
    assert report.periods == []


def test_bottleneck_counts_multi_skilled_researcher_once():
    users, visits, avail = _anna_bram_cees()

    report = _bottleneck_analysis(START, visits, users, avail)

    assert report.total_unmet_days == 1
    assert set(report.week_skills["2026-W20"]) <= {"Vleermuis", "SMP Vleermuis"}


def test_bottleneck_separates_committed_overbooking():
    """Two visits planned in week 20 with one night: overbooking, not a shortage."""
    users = [make_user(1, "vleermuis")]
    avail = _nights_per_week(1, range(20, 31))
    planned = [_week_visit(i, date(2026, 5, 11), date(2026, 7, 24)) for i in (1, 2)]
    for v in planned:
        v.planned_week = WEEK
    flexible = [_week_visit(3, date(2026, 5, 11), date(2026, 7, 24))]

    report = _bottleneck_analysis(START, planned + flexible, users, avail)

    assert report.total_unmet_days == 1
    assert report.committed_overbooked_days == 1
    assert report.committed_overbooked_visits == 1


@pytest.mark.parametrize("flow", [False, True])
def test_past_anchored_visits_do_not_count_as_overflow(profile_flow, monkeypatch, flow):
    """A visit planned in a week that has passed must not consume capacity."""
    from ortools.sat.python import cp_model

    import app.services.season_planning_service as sps

    profile_flow(flow)
    users = [make_user(1, "vleermuis")]
    avail = _nights_per_week(1, range(20, 31))
    past = _week_visit(1, date(2026, 4, 27), date(2026, 7, 24))
    past.planned_week = 18  # before START (week 20); no availability there
    upcoming = _week_visit(2, date(2026, 5, 11), date(2026, 7, 24))

    names: list[str] = []

    class Capture(cp_model.CpSolver):
        def Solve(self, model, *args, **kwargs):
            names.extend(v.name for v in model.Proto().variables)
            return super().Solve(model, *args, **kwargs)

    monkeypatch.setattr(sps.cp_model, "CpSolver", Capture)
    diagnostics = SeasonPlanningService.solve_season(
        START, [past, upcoming], users, avail, num_workers=1
    )

    assert _unscheduled(diagnostics) == set()
    assert not [n for n in names if n.startswith("overflow") and "_18_" in n]


def test_visit_without_protocol_and_week_reports_technical_problem(profile_flow):
    profile_flow(True)
    users = [make_user(1, "vleermuis")]
    avail = _nights_per_week(1, range(20, 31))
    orphan = _week_visit(1, date(2026, 5, 11), date(2026, 7, 24))
    orphan.protocol_visit_windows = []
    planned_orphan = _week_visit(2, date(2026, 5, 11), date(2026, 7, 24))
    planned_orphan.protocol_visit_windows = []
    planned_orphan.planned_week = WEEK  # fixed demand, handled by the planner

    diagnostics = SeasonPlanningService.solve_season(
        START, [orphan, planned_orphan], users, avail, num_workers=1
    )

    codes = {d.visit_id: d.details["reason_code"] for d in diagnostics}
    assert codes == {1: "technisch_probleem"}
    assert "support" in next(d.details["reason_nl"] for d in diagnostics)


def test_apply_unschedulable_totals_only_capacity_gaps():
    from app.schemas.capacity import (
        CapacityBottleneckReport,
        CapacitySimulationResponse,
    )

    vis = [
        SimpleNamespace(id=1, researchers=[1, 2], required_researchers=1),  # 2 days
        SimpleNamespace(id=2, researchers=[], required_researchers=3),  # 3 days
        SimpleNamespace(id=3, researchers=[], required_researchers=1),  # other reason
    ]
    for v in vis:
        v.cluster = None
        v.to_date = None
        v.part_of_day = None
        v.custom_function_name = v.custom_species_name = None
        v.functions = []
        v.species = []
        v.vog = False
    result = CapacitySimulationResponse(
        horizon_start=START,
        horizon_end=date(2026, 12, 31),
        grid={},
        bottlenecks=CapacityBottleneckReport(total_unmet_days=26),
    )
    entries = [
        (1, {"reason_code": "capaciteitsgebrek", "reason_nl": "x"}),
        (2, {"reason_code": "capaciteitsgebrek", "reason_nl": "x"}),
        (3, {"reason_code": "technisch_probleem", "reason_nl": "y"}),
    ]

    SeasonPlanningService._apply_unschedulable(result, vis, entries)

    assert len(result.unschedulable_visits) == 3
    assert result.bottlenecks.unscheduled_visits == 2
    assert result.bottlenecks.unscheduled_days == 5
