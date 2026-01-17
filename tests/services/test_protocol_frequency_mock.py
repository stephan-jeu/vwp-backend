import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import date, timedelta

# Import the functions to test. 
from app.services.visit_planning_selection import _eligible_visits_for_week
from app.services.visit_sanitization import sanitize_future_planning

@pytest.mark.asyncio
async def test_lookback_frequency_exclusion(mocker):
    """
    Verify _eligible_visits_for_week excludes candidates if a blocked protocol 
    is found in the lookback window.
    """
    
    # 1. Setup
    w20_monday = date.fromisocalendar(2026, 20, 1)
    
    # Mock DB
    mock_db = AsyncMock()
    
    # Mock synchronous begin/begin_nested returning async context manager
    mock_db.begin_nested = MagicMock()
    mock_db.begin_nested.return_value.__aenter__.return_value = None
    mock_db.begin_nested.return_value.__aexit__.side_effect = AsyncMock()

    mock_db.begin = MagicMock()
    mock_db.begin.return_value.__aenter__.return_value = None
    mock_db.begin.return_value.__aexit__.side_effect = AsyncMock()
    
    mock_db.in_transaction.return_value = True
    
    # Mock executions.
    # The function runs 2 queries:
    # 1. stmt_hist -> fetching blocked protocols with their min_period settings.
    #    Returns: (prot_id, min_val, min_unit, locked_visit_end, locked_week)
    
    # Let's say:
    # - Protocol 10: Min gap 3 weeks. Last visited Week 19 (End date 2026-05-08).
    # - Protocol 11: Min gap 1 week. Last visited Week 18.
    
    # Target week is Week 20 (Starts 2026-05-11).
    # Gap for P10: (May 11) - (May 8) = 3 days. Required: 21 days. -> BLOCKED.
    # Gap for P11: (May 11) - (Week 18 ~May 1) > 7 days. -> NOT BLOCKED.
    
    mock_result_hist = MagicMock()
    # Row format: (prot_id, min_val, min_unit, locked_visit_end, locked_week)
    rows = [
        (10, 3, 'weeks', date(2026, 5, 8), 19), 
        (11, 1, 'weeks', date(2026, 5, 1), 18)
    ]
    mock_result_hist.unique.return_value.all.return_value = rows
    
    mock_result_candidates = MagicMock()
    
    # Create Candidate Visits
    # Visit A: has Protocol 5 (OK - not in list)
    # Visit B: has Protocol 10 (BLOCKED)
    # Visit C: has Protocol 11 (OK - gap satisfied)
    
    cand_a = MagicMock(name="VisitA")
    cand_a.id=1
    pvw_a = MagicMock(protocol_id=5)
    cand_a.protocol_visit_windows = [pvw_a]
    
    cand_b = MagicMock(name="VisitB")
    cand_b.id=2
    pvw_b = MagicMock(protocol_id=10)
    cand_b.protocol_visit_windows = [pvw_b]
    
    cand_c = MagicMock(name="VisitC")
    cand_c.id=3
    pvw_c = MagicMock(protocol_id=11)
    cand_c.protocol_visit_windows = [pvw_c]
    
    mock_result_candidates.scalars.return_value.unique.return_value.all.return_value = [cand_a, cand_b, cand_c]
    
    mock_db.execute.side_effect = [mock_result_hist, mock_result_candidates]
    
    # 2. Execute
    results = await _eligible_visits_for_week(mock_db, w20_monday)
    
    # 3. Verify
    # Should contain cand_a and cand_c
    result_ids = [v.id for v in results]
    assert 1 in result_ids
    assert 3 in result_ids
    assert 2 not in result_ids # cand_b blocked
    

@pytest.mark.asyncio
async def test_lookahead_sanitization(mocker):
    """
    Verify sanitize_future_planning clears future locked visits if they conflict
    with newly planned visits based on protocol frequency.
    """
    
    # 1. Setup
    w20_monday = date.fromisocalendar(2026, 20, 1)
    # Week 20 ends roughly May 15th
    
    mock_db = AsyncMock()
    mock_db.begin = MagicMock()
    mock_db.begin.return_value.__aenter__.return_value = None
    mock_db.begin.return_value.__aexit__.side_effect = AsyncMock()
    
    # Newly planned visit: ID 100, Protocol 99
    newly_planned_ids = [100]
    
    # Mock queries:
    # 1. Fetch new visits (to find their protocols).
    mock_res_new = MagicMock()
    visit_new = MagicMock(id=100)
    pvw_new = MagicMock(protocol_id=99)
    visit_new.protocol_visit_windows = [pvw_new]
    mock_res_new.scalars.return_value.unique.return_value.all.return_value = [visit_new]
    
    # 2. Fetch future conflicts
    # Returns: (visit_future, prot_id, min_val, min_unit)
    
    # Visit Future A: Protocol 99. Planned Week 21 (Starts May 18).
    # New Plan Week 20 ends May 15. Gap: 3 days.
    # Protocol 99 req: 2 weeks (14 days). -> VIOLATION.
    
    # Visit Future B: Protocol 99. Planned Week 25 (Starts June 15).
    # Gap > 14 days. -> OK.
    
    visit_future_a = MagicMock(id=200, planned_week=21, from_date=date(2026, 5, 18))
    visit_future_a.researchers = ["mock_res"] 
    
    visit_future_b = MagicMock(id=300, planned_week=25, from_date=date(2026, 6, 15))
    visit_future_b.researchers = ["mock_res"]
    
    # Rows
    rows = [
        (visit_future_a, 99, 2, 'weeks'),
        (visit_future_b, 99, 2, 'weeks')
    ]
    
    mock_res_future = MagicMock()
    mock_res_future.unique.return_value.all.return_value = rows
    
    mock_db.execute.side_effect = [mock_res_new, mock_res_future]
    
    # 3. Execute
    sanitized = await sanitize_future_planning(mock_db, w20_monday, newly_planned_ids)
    
    # 4. Verify
    assert 200 in sanitized
    assert 300 not in sanitized
    
    # Check modification
    assert visit_future_a.planned_week is None
    # Verify researchers cleared (assuming mock list behavior or clear call)
    # Since it's a mock list, we can check if clear was called if it's a MagicMock, 
    # or if we used a real list ["mock_res"], check len.
    # Here we used a real list.
    assert len(visit_future_a.researchers) == 0
    
    mock_db.commit.assert_awaited_once()
