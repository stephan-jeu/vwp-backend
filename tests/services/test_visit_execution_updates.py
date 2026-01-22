import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date

from app.services.visit_execution_updates import update_subsequent_visits
from app.models.visit import Visit
from app.models.protocol import Protocol
from app.models.protocol_visit_window import ProtocolVisitWindow


@pytest.mark.asyncio
async def test_update_subsequent_visits_no_pvws():
    db = AsyncMock()
    visit = Visit(id=1)

    # Mock the initial fetch of the visit
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = visit
    # visit.protocol_visit_windows is empty or None
    visit.protocol_visit_windows = []

    db.execute.return_value = mock_result

    await update_subsequent_visits(db, visit, date(2025, 1, 1))

    # Should return early, no further db calls
    assert db.execute.call_count == 1


@pytest.mark.asyncio
async def test_update_subsequent_visits_updates_date():
    db = AsyncMock()
    db.add = MagicMock()

    # Setup data
    protocol = Protocol(
        id=10, min_period_between_visits_value=2, min_period_between_visits_unit="days"
    )

    pvw1 = ProtocolVisitWindow(id=100, protocol_id=10, visit_index=1, protocol=protocol)
    pvw2 = ProtocolVisitWindow(id=101, protocol_id=10, visit_index=2, protocol=protocol)

    executed_visit = Visit(id=1, cluster_id=5)
    executed_visit.protocol_visit_windows = [pvw1]

    target_visit = Visit(id=2, cluster_id=5, from_date=date(2025, 1, 2))
    target_visit.protocol_visit_windows = [pvw2]

    # Mock DB responses
    # 1. Fetch executed visit
    mock_res1 = MagicMock()
    mock_res1.scalars.return_value.first.return_value = executed_visit

    # 2. Fetch subsequent PVWs
    mock_res2 = MagicMock()
    mock_res2.scalars.return_value.all.return_value = [pvw2]

    # 3. Fetch linked visits
    mock_res3 = MagicMock()
    mock_res3.scalars.return_value.unique.return_value.all.return_value = [target_visit]

    db.execute.side_effect = [mock_res1, mock_res2, mock_res3]

    execution_date = date(2025, 1, 1)
    await update_subsequent_visits(db, executed_visit, execution_date)

    # Expected new date: 2025-01-01 + 2 days = 2025-01-03
    # Current date is 2025-01-02, so it should be updated
    assert target_visit.from_date == date(2025, 1, 3)
    db.add.assert_called_with(target_visit)


@pytest.mark.asyncio
async def test_update_subsequent_visits_no_update_needed():
    db = AsyncMock()

    # Setup data
    protocol = Protocol(
        id=10, min_period_between_visits_value=2, min_period_between_visits_unit="days"
    )

    pvw1 = ProtocolVisitWindow(id=100, protocol_id=10, visit_index=1, protocol=protocol)
    pvw2 = ProtocolVisitWindow(id=101, protocol_id=10, visit_index=2, protocol=protocol)

    executed_visit = Visit(id=1, cluster_id=5)
    executed_visit.protocol_visit_windows = [pvw1]

    # Target visit already has a later date
    target_visit = Visit(id=2, cluster_id=5, from_date=date(2025, 1, 5))
    target_visit.protocol_visit_windows = [pvw2]

    # Mock DB responses
    mock_res1 = MagicMock()
    mock_res1.scalars.return_value.first.return_value = executed_visit

    mock_res2 = MagicMock()
    mock_res2.scalars.return_value.all.return_value = [pvw2]

    mock_res3 = MagicMock()
    mock_res3.scalars.return_value.unique.return_value.all.return_value = [target_visit]

    db.execute.side_effect = [mock_res1, mock_res2, mock_res3]

    execution_date = date(2025, 1, 1)
    await update_subsequent_visits(db, executed_visit, execution_date)

    # Should NOT be updated
    assert target_visit.from_date == date(2025, 1, 5)
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_update_subsequent_visits_june_window_clamped_left():
    db = AsyncMock()
    db.add = MagicMock()

    # Arrange: 2-visit protocol requiring June, second visit window 28 May - 21 June
    protocol = Protocol(
        id=10,
        visits=2,
        min_period_between_visits_value=2,
        min_period_between_visits_unit="days",
        requires_june_visit=True,
    )

    pvw1 = ProtocolVisitWindow(id=100, protocol_id=10, visit_index=1, protocol=protocol)
    pvw2 = ProtocolVisitWindow(id=101, protocol_id=10, visit_index=2, protocol=protocol)

    executed_visit = Visit(id=1, cluster_id=5)
    executed_visit.protocol_visit_windows = [pvw1]

    target_visit = Visit(
        id=2,
        cluster_id=5,
        from_date=date(2025, 5, 28),
        to_date=date(2025, 6, 21),
    )
    target_visit.protocol_visit_windows = [pvw2]

    mock_res1 = MagicMock()
    mock_res1.scalars.return_value.first.return_value = executed_visit

    mock_res2 = MagicMock()
    mock_res2.scalars.return_value.all.return_value = [pvw2]

    mock_res3 = MagicMock()
    mock_res3.scalars.return_value.unique.return_value.all.return_value = [target_visit]

    db.execute.side_effect = [mock_res1, mock_res2, mock_res3]

    # Act
    execution_date = date(2025, 5, 1)
    await update_subsequent_visits(db, executed_visit, execution_date)

    # Assert: window is clamped to start of June but end date preserved
    assert target_visit.from_date == date(2025, 6, 1)
    assert target_visit.to_date == date(2025, 6, 21)
    db.add.assert_called_with(target_visit)


@pytest.mark.asyncio
async def test_update_subsequent_visits_june_window_clamped_both_sides():
    db = AsyncMock()
    db.add = MagicMock()

    # Arrange: 2-visit protocol requiring June, second visit window 25 May - 5 July
    protocol = Protocol(
        id=10,
        visits=2,
        min_period_between_visits_value=2,
        min_period_between_visits_unit="days",
        requires_june_visit=True,
    )

    pvw1 = ProtocolVisitWindow(id=100, protocol_id=10, visit_index=1, protocol=protocol)
    pvw2 = ProtocolVisitWindow(id=101, protocol_id=10, visit_index=2, protocol=protocol)

    executed_visit = Visit(id=1, cluster_id=5)
    executed_visit.protocol_visit_windows = [pvw1]

    target_visit = Visit(
        id=2,
        cluster_id=5,
        from_date=date(2025, 5, 25),
        to_date=date(2025, 7, 5),
    )
    target_visit.protocol_visit_windows = [pvw2]

    mock_res1 = MagicMock()
    mock_res1.scalars.return_value.first.return_value = executed_visit

    mock_res2 = MagicMock()
    mock_res2.scalars.return_value.all.return_value = [pvw2]

    mock_res3 = MagicMock()
    mock_res3.scalars.return_value.unique.return_value.all.return_value = [target_visit]

    db.execute.side_effect = [mock_res1, mock_res2, mock_res3]

    # Act
    execution_date = date(2025, 5, 1)
    await update_subsequent_visits(db, executed_visit, execution_date)

    # Assert: window is fully clamped to June
    assert target_visit.from_date == date(2025, 6, 1)
    assert target_visit.to_date == date(2025, 6, 30)
    db.add.assert_called_with(target_visit)


@pytest.mark.asyncio
async def test_update_subsequent_visits_june_requirement_ignored_when_execution_in_june():
    db = AsyncMock()
    db.add = MagicMock()

    # Arrange: requirement is present but execution happens in June, so no June clamp
    protocol = Protocol(
        id=10,
        visits=2,
        min_period_between_visits_value=2,
        min_period_between_visits_unit="days",
        requires_june_visit=True,
    )

    pvw1 = ProtocolVisitWindow(id=100, protocol_id=10, visit_index=1, protocol=protocol)
    pvw2 = ProtocolVisitWindow(id=101, protocol_id=10, visit_index=2, protocol=protocol)

    executed_visit = Visit(id=1, cluster_id=5)
    executed_visit.protocol_visit_windows = [pvw1]

    target_visit = Visit(
        id=2,
        cluster_id=5,
        from_date=date(2025, 6, 10),
        to_date=date(2025, 7, 5),
    )
    target_visit.protocol_visit_windows = [pvw2]

    mock_res1 = MagicMock()
    mock_res1.scalars.return_value.first.return_value = executed_visit

    mock_res2 = MagicMock()
    mock_res2.scalars.return_value.all.return_value = [pvw2]

    mock_res3 = MagicMock()
    mock_res3.scalars.return_value.unique.return_value.all.return_value = [target_visit]

    db.execute.side_effect = [mock_res1, mock_res2, mock_res3]

    # Act: execution takes place in June
    execution_date = date(2025, 6, 1)
    await update_subsequent_visits(db, executed_visit, execution_date)

    # Assert: dates are unchanged and June-specific logic does not fire
    assert target_visit.from_date == date(2025, 6, 10)
    assert target_visit.to_date == date(2025, 7, 5)
    db.add.assert_not_called()
