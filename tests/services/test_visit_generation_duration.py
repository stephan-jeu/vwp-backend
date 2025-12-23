
from datetime import date, time
from app.models.protocol import Protocol
from app.services.visit_generation_common import calculate_visit_props

def test_calculate_duration_pure_absolute_time_crossing_midnight():
    # Case: p1 starts 22:00 (1h), p2 starts 00:00 (2h).
    # Expected span: 22:00 to 02:00 = 4 hours (240 mins)
    
    p1 = Protocol(
        id=1,
        start_timing_reference="ABSOLUTE_TIME",
        start_time_absolute_from=time(22, 0),
        visit_duration_hours=1.0
    )
    p2 = Protocol(
        id=2,
        start_timing_reference="ABSOLUTE_TIME",
        start_time_absolute_from=time(0, 0),
        visit_duration_hours=2.0
    )
    
    # We pass a dummy reference date, though pure absolute logic might not need it if ignoring seasons
    # But for consistency we provide one.
    ref_date = date(2025, 6, 1) 
    
    duration, text = calculate_visit_props([p1, p2], "Avond", reference_date=ref_date)
    assert duration == 240, f"Expected 240 min, got {duration}"
    # The text is usually the start time of the combined visit. Earliest is 22:00.
    assert text == "22:00", f"Expected '22:00', got {text}"

def test_calculate_duration_pure_absolute_time_simple():
    # Case: p1 starts 20:00 (2h), p2 starts 21:00 (1h).
    # Span: 20:00 to 22:00 = 2 hours (120 min)
    p1 = Protocol(
        id=1,
        start_timing_reference="ABSOLUTE_TIME",
        start_time_absolute_from=time(20, 0),
        visit_duration_hours=2.0
    )
    p2 = Protocol(
        id=2,
        start_timing_reference="ABSOLUTE_TIME",
        start_time_absolute_from=time(21, 0),
        visit_duration_hours=1.0
    )
    ref_date = date(2025, 6, 1)
    duration, text = calculate_visit_props([p1, p2], "Avond", reference_date=ref_date)
    assert duration == 120
    assert text == "20:00"

def test_calculate_duration_mixed_absolute_sunset_august():
    # Month August (8) -> Sunset assumed 21:00
    # p1: Absolute 23:00 (1h) -> Ends 24:00 (00:00 next day)
    # p2: Sunset + 60 min (1h) -> 21:00 + 1h = 22:00 start -> Ends 23:00
    # Combined: Earliest Start 22:00. Latest End 24:00.
    # Expected Duration: 2 hours (120 min)
    
    p1 = Protocol(
        id=1,
        start_timing_reference="ABSOLUTE_TIME",
        start_time_absolute_from=time(23, 0),
        visit_duration_hours=1.0
    )
    p2 = Protocol(
        id=2,
        start_timing_reference="SUNSET",
        start_time_relative_minutes=60,
        visit_duration_hours=1.0
    )
    
    ref_date_aug = date(2025, 8, 15)
    
    duration, text = calculate_visit_props([p1, p2], "Avond", reference_date=ref_date_aug)
    
    # 21:00 (Sunset) + 60 = 22:00. 
    # Absolute 23:00.
    # Earliest start = 22:00.
    # Ends: 23:00 (1h after 22:00) vs 00:00 (1h after 23:00).
    # Span: 22:00 to 00:00 = 120 min.
    assert duration == 120
    # Text logic fallback might be complex, but for now we check duration primarily.
    # Ideally standard logic picks earliest.
    # But mixed text might depend on what `calculate_visit_props` decides.
    # User didn't specify text requirements for mixed, only duration correct calculation.
