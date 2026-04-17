from datetime import date
from types import SimpleNamespace
from app.services.season_planning_service import SeasonPlanningService


def make_visit(vid, skill="Vleermuis"):
    # Using SimpleNamespace to avoid MagicMock truthy traps
    v = SimpleNamespace(
        id=vid,
        sleutel=False,
        cluster=SimpleNamespace(project_id=1),
        from_date=date(2025, 1, 1),
        to_date=date(2025, 12, 31),
        planned_week=None,
        provisional_week=None,
        provisional_locked=False,
        custom_function_name=None,
        custom_species_name=None,
        required_researchers=1,
        functions=[],
    )

    # Required Skill
    fam = SimpleNamespace(name=skill)
    sp = SimpleNamespace(family=fam)
    v.species = [sp]

    # Protocol Window
    pvw = SimpleNamespace()
    proto = SimpleNamespace()
    proto.id = 1
    proto.min_period_between_visits_value = 0
    proto.min_period_between_visits_unit = "days"
    pvw.protocol = proto
    pvw.protocol_id = 1
    pvw.visit_index = 1
    v.protocol_visit_windows = [pvw]

    # The service expects cluster_id
    v.cluster_id = 1

    return v


def test_zero_supply_prevents_assignment():
    # Scenario: Week 1 has 0 Supply. Week 11 has Supply.
    # Visit should go to Week 11.

    v1 = make_visit(101)

    # User 1: Has Skill Vleermuis.
    u1 = SimpleNamespace(
        id=1,
        vleermuis=True,
        smp_vleermuis=False,
        smp_gierzwaluw=False,
        smp_huismus=False,
        vrfg=False,
        langoor=False,
        schijfhoren=False,
        zwaluw=False,
        vlinder=False,
        teunisbloempijlstaart=False,
        zangvogel=False,
        roofvogel=False,
        pad=False,
        biggenkruid=False,
        contract_type="medewerker",
        experience_bat="medior",
        deleted_at=None,
    )

    # Availability Map
    # Week 10: 0 Days
    # Week 11: 5 Days
    # We span 1..52
    avail_map = {}

    # Target week 11: 5 days availability
    avail_map[(1, 11)] = SimpleNamespace(
        user_id=1,
        week=11,
        morning_days=5,
        daytime_days=5,
        nighttime_days=5,
        flex_days=0,
    )

    # All other weeks 1..52 are 0
    for w in range(1, 54):
        if w != 11:
            avail_map[(1, w)] = SimpleNamespace(
                user_id=1,
                week=w,
                morning_days=0,
                daytime_days=0,
                nighttime_days=0,
                flex_days=0,
            )

    start_date = date(2025, 1, 1)

    # RUN
    SeasonPlanningService.solve_season(start_date, [v1], [u1], avail_map)

    # It must NOT be Week 1 (Zero Supply)
    assert v1.provisional_week != 1

    # It must be Week 11
    assert v1.provisional_week == 11


def test_daypart_capacity_prevents_evening_assignment_to_morning_only_week():
    # Scenario:
    # - Visit requires evening execution (part_of_day="Avond")
    # - Week 11 only has morning capacity (nighttime=0, flex=0)
    # Expectation: visit is not assigned to week 11.

    v1 = make_visit(201)
    v1.part_of_day = "Avond"

    u1 = SimpleNamespace(
        id=1,
        vleermuis=True,
        smp_vleermuis=False,
        smp_gierzwaluw=False,
        smp_huismus=False,
        vrfg=False,
        langoor=False,
        schijfhoren=False,
        zwaluw=False,
        vlinder=False,
        teunisbloempijlstaart=False,
        zangvogel=False,
        roofvogel=False,
        pad=False,
        biggenkruid=False,
        contract=None,
        experience_bat="Medior",
        deleted_at=None,
    )

    avail_map = {}

    # Week 11 has *only* morning capacity.
    avail_map[(1, 11)] = SimpleNamespace(
        user_id=1,
        week=11,
        morning_days=5,
        daytime_days=0,
        nighttime_days=0,
        flex_days=0,
    )

    for w in range(1, 54):
        if w != 11:
            avail_map[(1, w)] = SimpleNamespace(
                user_id=1,
                week=w,
                morning_days=0,
                daytime_days=0,
                nighttime_days=0,
                flex_days=0,
            )

    start_date = date(2025, 1, 1)

    # RUN
    SeasonPlanningService.solve_season(start_date, [v1], [u1], avail_map)

    # ASSERT: evening visit cannot use morning-only capacity
    assert v1.provisional_week != 11


def test_smp_visit_requires_smp_skill_for_assignment():
    v1 = make_visit(301, skill="Vleermuis")
    v1.functions = [SimpleNamespace(name="SMP Inventarisatie")]

    u1 = SimpleNamespace(
        id=1,
        vleermuis=True,
        smp_vleermuis=False,
        smp_gierzwaluw=False,
        smp_huismus=False,
        vrfg=False,
        langoor=False,
        schijfhoren=False,
        zwaluw=False,
        vlinder=False,
        teunisbloempijlstaart=False,
        zangvogel=False,
        roofvogel=False,
        pad=False,
        biggenkruid=False,
        contract=None,
        experience_bat="Medior",
        deleted_at=None,
    )

    avail_map = {
        (1, 11): SimpleNamespace(
            user_id=1,
            week=11,
            morning_days=5,
            daytime_days=5,
            nighttime_days=5,
            flex_days=0,
        )
    }

    start_date = date(2025, 1, 1)

    SeasonPlanningService.solve_season(start_date, [v1], [u1], avail_map)

    assert v1.provisional_week is None


def test_smp_visit_can_be_assigned_with_matching_smp_skill():
    v1 = make_visit(302, skill="Vleermuis")
    v1.functions = [SimpleNamespace(name="SMP Inventarisatie")]

    u1 = SimpleNamespace(
        id=1,
        vleermuis=False,
        smp_vleermuis=True,
        smp_gierzwaluw=False,
        smp_huismus=False,
        vrfg=False,
        langoor=False,
        schijfhoren=False,
        zwaluw=False,
        vlinder=False,
        teunisbloempijlstaart=False,
        zangvogel=False,
        roofvogel=False,
        pad=False,
        biggenkruid=False,
        contract=None,
        experience_bat="Medior",
        deleted_at=None,
    )

    avail_map = {
        (1, 11): SimpleNamespace(
            user_id=1,
            week=11,
            morning_days=5,
            daytime_days=5,
            nighttime_days=5,
            flex_days=0,
        )
    }

    start_date = date(2025, 1, 1)

    SeasonPlanningService.solve_season(start_date, [v1], [u1], avail_map)

    assert v1.provisional_week == 11


def test_quadratic_load_distributes_evenly():
    """Quadratic load penalty spreads visits across available weeks.

    With the penalty enabled, 10 visits valid in weeks 10–11 should be
    distributed across both weeks instead of all landing in week 10
    (which the slack_penalty alone would cause).
    """
    from unittest.mock import MagicMock, patch

    start_date = date(2025, 3, 3)  # ISO week 10

    def make_spread_visit(vid):
        return SimpleNamespace(
            id=vid,
            sleutel=False,
            cluster=SimpleNamespace(project_id=vid),
            cluster_id=vid,
            from_date=date(2025, 3, 3),  # week 10
            to_date=date(2025, 3, 14),  # week 11
            planned_week=None,
            provisional_week=None,
            provisional_locked=False,
            custom_function_name=None,
            custom_species_name=None,
            required_researchers=1,
            functions=[],
            protocol_visit_windows=[],
            species=[SimpleNamespace(family=SimpleNamespace(name="Vleermuis"))],
        )

    u1 = SimpleNamespace(
        id=1,
        vleermuis=True,
        smp_vleermuis=False,
        smp_gierzwaluw=False,
        smp_huismus=False,
        vrfg=False,
        langoor=False,
        schijfhoren=False,
        zwaluw=False,
        vlinder=False,
        teunisbloempijlstaart=False,
        zangvogel=False,
        roofvogel=False,
        pad=False,
        biggenkruid=False,
        contract_type="medewerker",
        experience_bat="medior",
        deleted_at=None,
    )

    avail_map = {}
    for w in range(1, 54):
        avail_map[(1, w)] = SimpleNamespace(
            user_id=1,
            week=w,
            morning_days=20,
            daytime_days=0,
            nighttime_days=0,
            flex_days=0,
        )

    # --- Met spread penalty (expliciet aan) ---
    visits = [make_spread_visit(i) for i in range(1, 11)]
    mock_settings_on = MagicMock()
    mock_settings_on.constraint_quadratic_load_penalty = True
    mock_settings_on.constraint_quadratic_load_penalty_weight = 5
    mock_settings_on.constraint_large_team_penalty = False
    mock_settings_on.provisional_week_stickiness_enabled = False
    mock_settings_on.season_planner_avoid_current_week_penalty = 0
    with patch(
        "app.services.season_planning_service.get_settings",
        return_value=mock_settings_on,
    ):
        SeasonPlanningService.solve_season(start_date, visits, [u1], avail_map)
    weeks_assigned = [v.provisional_week for v in visits if v.provisional_week]
    assert len(weeks_assigned) == 10
    assert 10 in weeks_assigned and 11 in weeks_assigned, (
        "Spread penalty moet bezoeken over weken 10 én 11 verdelen"
    )

    # --- Zonder spread penalty: alles in week 10 (front-loading) ---
    visits2 = [make_spread_visit(100 + i) for i in range(1, 11)]
    mock_settings = MagicMock()
    mock_settings.constraint_quadratic_load_penalty = False
    mock_settings.constraint_quadratic_load_penalty_weight = 0
    mock_settings.constraint_large_team_penalty = False
    mock_settings.provisional_week_stickiness_enabled = False
    mock_settings.season_planner_avoid_current_week_penalty = 0
    with patch(
        "app.services.season_planning_service.get_settings", return_value=mock_settings
    ):
        SeasonPlanningService.solve_season(start_date, visits2, [u1], avail_map)
    weeks_no_spread = [v.provisional_week for v in visits2 if v.provisional_week]
    assert all(w == 10 for w in weeks_no_spread), (
        "Zonder spread penalty moeten bezoeken front-loaded in week 10 staan"
    )
