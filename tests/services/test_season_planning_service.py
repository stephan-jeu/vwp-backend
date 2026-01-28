from datetime import date
from unittest.mock import MagicMock
from app.services.season_planning_service import SeasonPlanningService


def make_visit(
    id,
    cluster_id,
    protocol_id,
    visit_index,
    min_gap_val=None,
    min_gap_unit=None,
    window_from: date | None = None,
):
    v = MagicMock()
    v.id = id
    v.cluster_id = cluster_id
    v.part_of_day = "Ochtend"
    v.from_date = date(2026, 1, 1)
    v.to_date = date(2026, 12, 31)
    v.planned_week = None
    v.provisional_locked = False
    v.active = True
    v.required_researchers = 1

    # Custom/Smp logic bypass
    v.custom_function_name = None
    v.custom_species_name = None

    # Protocol Structure
    # v.protocol_visit_windows[0].protocol
    pvw = MagicMock()
    pvw.protocol_id = protocol_id
    pvw.visit_index = visit_index
    pvw.window_from = window_from or date(2026, 1, 1)

    proto = MagicMock()
    proto.min_period_between_visits_value = min_gap_val
    proto.min_period_between_visits_unit = min_gap_unit

    pvw.protocol = proto
    v.protocol_visit_windows = [pvw]

    v.protocol_visit_windows = [pvw]

    # Custom/Attributes defaults
    v.sleutel = False
    v.cluster = MagicMock()
    v.cluster.project_id = cluster_id * 100  # Unique per cluster

    # Function defaults
    fn = MagicMock()
    fn.name = "Inventarisatie"
    v.functions = [fn]

    # Mock behavior for attribute access if needed
    # Service accesses: v.from_date, v.to_date, v.cluster_id, v.protocol_visit_windows
    return v


def test_sequence_constraint_strict_order():
    # V1 (Index 1) and V2 (Index 2) for same cluster/protocol
    v1 = make_visit(
        101,
        cluster_id=1,
        protocol_id=10,
        visit_index=1,
        window_from=date(2026, 1, 1),
    )
    v2 = make_visit(
        102,
        cluster_id=1,
        protocol_id=10,
        visit_index=2,
        window_from=date(2026, 2, 1),
    )

    visits = [v1, v2]
    # One user with plenty capacity
    u1 = MagicMock()
    u1.id = 1
    # Skill keys? Service logic mocks this via _get_user_skill_keys and _get_required_user_flag
    # We need to make sure _get_required_user_flag(v) matches _get_user_skill_keys(u)
    # Service _get_required_user_flag accesses v.species...
    # Let's mock _get_required_user_flag static method?
    # Or just set v.species[0].family.name = "Vleermuis" and u1.vleermuis = True

    sp = MagicMock()
    sp.family.name = "Vleermuis"
    v1.species = [sp]
    v2.species = [sp]

    u1.vleermuis = True
    # Ensure other flags false to avoid noise
    u1.smp_vleermuis = False
    u1.smp_gierzwaluw = False
    u1.smp_huismus = False
    u1.vrfg = False
    u1.langoor = False
    u1.schijfhoren = False
    u1.zwaluw = False
    u1.vlinder = False
    u1.teunisbloempijlstaart = False
    u1.zangvogel = False
    u1.roofvogel = False
    u1.pad = False
    u1.biggenkruid = False

    users = [u1]
    # Add u2 to ensure plenty of capacity
    u2 = MagicMock()
    u2.id = 2
    u2.vleermuis = True
    users.append(u2)

    # Avail Map: User 1 available all year
    start_date = date(2026, 1, 1)
    avail_map = {}
    for w in range(1, 54):
        aw = MagicMock()
        # Explicitly set all to avoid MagicMock-as-int failure
        aw.configure_mock(morning_days=5, daytime_days=5, nighttime_days=5, flex_days=0)
        avail_map[(1, w)] = aw

    SeasonPlanningService.solve_season(start_date, visits, users, avail_map)

    print(f"V1 Week: {v1.provisional_week}")
    print(f"V2 Week: {v2.provisional_week}")

    assert v1.provisional_week is not None
    assert v2.provisional_week is not None
    assert v2.provisional_week > v1.provisional_week


def test_gap_constraint_min_period():
    # V1, V2 with 3 week gap (21 days)
    # 21 days / 7 = 3.0 -> 3 weeks gap
    v1 = make_visit(
        201,
        cluster_id=2,
        protocol_id=20,
        visit_index=1,
        min_gap_val=21,
        min_gap_unit="days",
        window_from=date(2026, 1, 1),
    )
    v2 = make_visit(
        202,
        cluster_id=2,
        protocol_id=20,
        visit_index=2,
        min_gap_val=21,
        min_gap_unit="days",
        window_from=date(2026, 2, 1),
    )

    sp = MagicMock()
    sp.family.name = "Vleermuis"
    v1.species = [sp]
    v2.species = [sp]

    u1 = MagicMock()
    u1.id = 1
    u1.vleermuis = True
    # Defaults
    u1.smp_vleermuis = False
    u1.smp_gierzwaluw = False
    u1.smp_huismus = False
    u1.vrfg = False
    u1.langoor = False
    u1.schijfhoren = False
    u1.zwaluw = False
    u1.vlinder = False
    u1.teunisbloempijlstaart = False
    u1.zangvogel = False
    u1.roofvogel = False
    u1.pad = False
    u1.biggenkruid = False

    visits = [v1, v2]
    users = [u1]

    start_date = date(2026, 1, 1)
    avail_map = {}
    for w in range(1, 54):
        aw = MagicMock()
        aw.configure_mock(morning_days=5, daytime_days=5, nighttime_days=5, flex_days=0)
        avail_map[(1, w)] = aw

    SeasonPlanningService.solve_season(start_date, visits, users, avail_map)

    print(f"V1 Week: {v1.provisional_week}")
    print(f"V2 Week: {v2.provisional_week}")

    assert v1.provisional_week is not None
    assert v2.provisional_week is not None

    # Gap enforcement
    # Constraint code: w2 >= w1 + 3
    assert v2.provisional_week >= v1.provisional_week + 3


def test_sleutel_constraint_intern_demand():
    # Visit requires sleutel -> Needs Intern
    # Week 10: 0 Interns. Week 11: 1 Intern.
    # Visit should be pushed to Week 11.

    v = make_visit(300, cluster_id=3, protocol_id=30, visit_index=1)
    v.sleutel = True
    v.from_date = date(2026, 1, 1)  # Start early

    # User 1: Senior (Not Intern). Available all year.
    u1 = MagicMock()
    u1.id = 1
    u1.contract_type = "Fixed"
    u1.experience_bat = "Senior"
    u1.vleermuis = True

    # User 2: Intern. Only available from Week 11.
    u2 = MagicMock()
    u2.id = 2
    u2.contract_type = "Intern"
    u2.experience_bat = "Junior"
    u2.vleermuis = True

    users = [u1, u2]
    visits = [v]

    sp = MagicMock()
    sp.family.name = "Vleermuis"
    v.species = [sp]

    # Avail Map
    start_date = date(2026, 1, 1)
    avail_map = {}

    for w in range(1, 54):
        # U1 always available
        aw1 = MagicMock()
        aw1.configure_mock(
            morning_days=5, daytime_days=5, nighttime_days=5, flex_days=0
        )
        avail_map[(1, w)] = aw1

        # U2 available only >= Week 11
        if w >= 11:
            aw2 = MagicMock()
            aw2.configure_mock(
                morning_days=5, daytime_days=5, nighttime_days=5, flex_days=0
            )
            avail_map[(2, w)] = aw2
        else:
            # U2 not available
            pass

    SeasonPlanningService.solve_season(start_date, visits, users, avail_map)

    print(f"Sleutel Visit Week: {v.provisional_week}")

    assert v.provisional_week is not None
    assert v.provisional_week >= 11


def test_coupling_constraint_supervisor_soft():
    # Visit: 2 researchers.
    # Week 20: 2 Juniors, 0 Seniors. (Shortfall Supervisor -> Penalty)
    # Week 21: 1 Junior, 1 Senior. (No Shortfall -> Preferred)
    # Solver should pick Week 21 to avoid penalty.

    v = make_visit(400, cluster_id=4, protocol_id=40, visit_index=1)
    v.required_researchers = 2
    v.from_date = date(2026, 5, 1)  # roughly week 18+
    v.to_date = date(2026, 6, 30)  # Allow scheduling up to Week ~26

    # U1: Junior (available W20, W21)
    u1 = MagicMock()
    u1.id = 1
    u1.contract_type = "Flex"  # Junior
    u1.experience_bat = "Junior"
    u1.vleermuis = True

    # U2: Junior (available W20, W21)
    u2 = MagicMock()
    u2.id = 2
    u2.contract_type = "Flex"  # Junior
    u2.experience_bat = "Junior"
    u2.vleermuis = True

    # U3: Medior (Available ONLY W21)
    u3 = MagicMock()
    u3.id = 3
    u3.contract_type = "Fixed"
    u3.experience_bat = "Medior"
    u3.vleermuis = True

    users = [u1, u2, u3]
    visits = [v]

    sp = MagicMock()
    sp.family.name = "Vleermuis"
    v.species = [sp]

    avail_map = {}
    start_date = date(2026, 1, 1)

    for w in [20, 21]:
        # U1, U2 available both weeks
        aw1 = MagicMock()
        aw1.configure_mock(
            morning_days=5, daytime_days=0, nighttime_days=0, flex_days=0
        )
        avail_map[(1, w)] = aw1

        aw2 = MagicMock()
        aw2.configure_mock(
            morning_days=5, daytime_days=0, nighttime_days=0, flex_days=0
        )
        avail_map[(2, w)] = aw2

        if w == 21:
            aw3 = MagicMock()
            aw3.configure_mock(
                morning_days=5, daytime_days=0, nighttime_days=0, flex_days=0
            )
            avail_map[(3, w)] = aw3

    SeasonPlanningService.solve_season(start_date, visits, users, avail_map)

    print(f"Coupling Visit Week: {v.provisional_week}")

    # Should pick W21 because W20 has Supervisor Shortfall (Soft Penalty)
    assert v.provisional_week == 21


def test_coupling_constraint_ignores_non_vleermuis():
    # Visit: 2 researchers, non-Vleermuis.
    # Week 20: 2 Juniors, 0 Seniors. (No supervisor penalty expected.)
    # Week 21: 1 Junior, 1 Medior.
    # Solver should pick Week 20 because it is earlier and no coupling penalty applies.

    v = make_visit(500, cluster_id=5, protocol_id=50, visit_index=1)
    v.required_researchers = 2
    v.from_date = date(2026, 5, 1)  # roughly week 18+
    v.to_date = date(2026, 6, 30)  # Allow scheduling up to Week ~26

    # U1: Junior (available W20, W21)
    u1 = MagicMock()
    u1.id = 1
    u1.contract_type = "Flex"  # Junior
    u1.experience_bat = "Junior"
    u1.vleermuis = True

    # U2: Junior (available W20, W21)
    u2 = MagicMock()
    u2.id = 2
    u2.contract_type = "Flex"  # Junior
    u2.experience_bat = "Junior"
    u2.vleermuis = True

    # U3: Medior (Available ONLY W21)
    u3 = MagicMock()
    u3.id = 3
    u3.contract_type = "Fixed"
    u3.experience_bat = "Medior"
    u3.vleermuis = True

    users = [u1, u2, u3]
    visits = [v]

    sp = MagicMock()
    sp.family.name = "Zwaluw"
    v.species = [sp]

    avail_map = {}
    start_date = date(2026, 1, 1)

    for w in [20, 21]:
        # U1, U2 available both weeks
        aw1 = MagicMock()
        aw1.configure_mock(
            morning_days=5, daytime_days=0, nighttime_days=0, flex_days=0
        )
        avail_map[(1, w)] = aw1

        aw2 = MagicMock()
        aw2.configure_mock(
            morning_days=5, daytime_days=0, nighttime_days=0, flex_days=0
        )
        avail_map[(2, w)] = aw2

        if w == 21:
            aw3 = MagicMock()
            aw3.configure_mock(
                morning_days=5, daytime_days=0, nighttime_days=0, flex_days=0
            )
            avail_map[(3, w)] = aw3

    SeasonPlanningService.solve_season(start_date, visits, users, avail_map)

    print(f"Non-bat Coupling Visit Week: {v.provisional_week}")

    # Should pick W20 because no Vleermuis coupling penalty applies.
    assert v.provisional_week == 20
