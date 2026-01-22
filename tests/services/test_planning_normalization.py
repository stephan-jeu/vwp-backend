import pytest
from unittest.mock import MagicMock, AsyncMock
from app.services.visit_planning_selection import select_visits_for_week
from datetime import date, timedelta


@pytest.mark.asyncio
async def test_select_visits_destructive_normalization_mock(mocker):
    """
    Verify that select_visits_for_week triggers destructive normalization
    on visit objects (sets planned_week=None) even during simulation.
    Uses Mocks to avoid DB interaction.
    """

    # 1. Setup Data
    w20_monday = date.fromisocalendar(2026, 20, 1)

    # Mock Visit object
    # We use a MagicMock that acts like a Visit
    visit_mock = MagicMock(name="VisitMock")
    visit_mock.id = 1
    visit_mock.planned_week = 20
    visit_mock.researchers = []  # Empty list = No researchers
    visit_mock.from_date = w20_monday
    visit_mock.to_date = w20_monday + timedelta(days=4)
    # Ensure it behaves like an object for getattr
    visit_mock.functions = []
    visit_mock.species = []
    visit_mock.protocol_visit_windows = []
    visit_mock.part_of_day = "Ochtend"
    visit_mock.required_researchers = 1

    # Needs cluster address for travel time check
    visit_mock.cluster.address = "Test Address"
    visit_mock.cluster.project.location = "Test City"
    visit_mock.cluster.project_id = 100

    # 2. Mock Dependencies
    # We need to mock _eligible_visits_for_week to return our visit
    mocker.patch(
        "app.services.visit_planning_selection._eligible_visits_for_week",
        new_callable=AsyncMock,
        return_value=[visit_mock],
    )

    mocker.patch(
        "app.services.visit_planning_selection._load_week_capacity",
        new_callable=AsyncMock,
        return_value={"Ochtend": 10, "Flex": 10},  # Sufficient capacity
    )

    # Mock other DB loaders to avoid 'execute' calls
    mocker.patch(
        "app.services.visit_planning_selection._load_all_users",
        new_callable=AsyncMock,
        return_value=[],
    )
    mocker.patch(
        "app.services.visit_planning_selection._load_user_capacities",
        new_callable=AsyncMock,
        return_value={},
    )
    mocker.patch(
        "app.services.visit_planning_selection._load_user_daypart_capacities",
        new_callable=AsyncMock,
        return_value={},
    )
    mocker.patch(
        "app.services.visit_planning_selection._apply_existing_assignments_to_capacities",
        new_callable=AsyncMock,
        return_value=None,
    )

    # Mock status resolution so it doesn't filter out our visit
    # We mock resolve_visit_status to return OPEN
    from app.services.visit_status_service import VisitStatusCode

    mocker.patch(
        "app.services.visit_planning_selection.resolve_visit_status",
        new_callable=AsyncMock,
        return_value=VisitStatusCode.OPEN,
    )

    # Mock derive_visit_status as well just in case
    mocker.patch(
        "app.services.visit_planning_selection.derive_visit_status",
        return_value=VisitStatusCode.OPEN,
    )

    # Mock DB session (can be a standard AsyncMock), BUT we pass None to trigger _core logic
    mock_db = None

    # 3. Execution
    await select_visits_for_week(mock_db, w20_monday, timeout_seconds=0.1)

    # 4. Verify Side Effect
    # Did the code set visit_mock.planned_week = None?

    # Logic in code:
    # if has_planned_week and not has_researchers:
    #    v.planned_week = None

    # Because visit_mock is a MagicMock, assigments are recorded.
    # We can check if the attribute was mutated.

    # If the bug exists, this assertion passes (normalization happened)
    # But wait, we want to fail if the bug exists?
    # Usually reproduction tests assert the *correct* behavior and fail if bug exists.
    # The correct behavior is: IT SHOULD NOT CHANGE.

    assert visit_mock.planned_week == 20, (
        "Destructive Normalization detected: planned_week was set to None!"
    )
