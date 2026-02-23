from datetime import date, time
from app.models.protocol import Protocol
from app.models.species import Species
from app.models.function import Function
from app.services.visit_generation_common import calculate_visit_props

def test_massawinterverblijf_single_protocol():
    """Test that a single Massawinterverblijfplaats protocol works according to standard logic."""
    p1 = Protocol(
        id=1,
        function=Function(name="Massawinterverblijfplaats", id=1),
        start_timing_reference="ABSOLUTE_TIME",
        start_time_absolute_from=time(0, 0),
        visit_duration_hours=1.0,
    )
    
    reference_date = date(2025, 6, 1)
    duration, text, _ = calculate_visit_props([p1], "Avond", reference_date=reference_date)
    
    # Defaults to max duration (60 mins) and we let standard absolute time logic handle text or returns None 
    # if our text search has not triggered "00:00" explicitly, but wait, if it fell through, it would do standard 
    # calculation. Let's make sure it matches the standard absolute time logic.
    assert duration == 60
    assert text == "00:00"

def test_massawinterverblijf_combined_non_mv_paarverblijf():
    """Test that Massawinterverblijfplaats combined with a non-MV Paarverblijf gives 00:00 and 120 mins."""
    p_massa = Protocol(
        id=1,
        function=Function(name="Massawinterverblijfplaats", id=1),
        start_timing_reference="ABSOLUTE_TIME",
        start_time_absolute_from=time(0, 0),
        visit_duration_hours=1.0,
    )
    p_paar = Protocol(
        id=2,
        function=Function(name="Paarverblijf", id=2),
        species=Species(name="Laatvlieger", abbreviation="LAAT", id=1),
        start_timing_reference="SUNSET",
        start_time_relative_minutes=0,
        visit_duration_hours=2.0,
    )
    
    reference_date = date(2025, 6, 1)
    duration, text, _ = calculate_visit_props([p_massa, p_paar], "Avond", reference_date=reference_date)
    
    assert duration == 120, f"Expected 120 min, got {duration}"
    assert text == "00:00", f"Expected '00:00', got {text}"

def test_massawinterverblijf_combined_mv_paarverblijf():
    """Test that Massawinterverblijfplaats combined with an MV Paarverblijf gives Zonsondergang."""
    p_massa = Protocol(
        id=1,
        function=Function(name="Massawinterverblijfplaats", id=1),
        start_timing_reference="ABSOLUTE_TIME",
        start_time_absolute_from=time(0, 0),
        visit_duration_hours=1.0,
    )
    p_paar = Protocol(
        id=2,
        function=Function(name="Paarverblijf", id=2),
        species=Species(name="Meervleermuis", abbreviation="MV", id=1), # MV!
        start_timing_reference="SUNSET",
        start_time_relative_minutes=0,
        visit_duration_hours=2.5,
    )
    
    reference_date = date(2025, 6, 1)
    duration, text, _ = calculate_visit_props([p_massa, p_paar], "Avond", reference_date=reference_date)
    
    assert duration == 150, f"Expected 150 mins max duration, got {duration}"
    assert text == "Zonsondergang", f"Expected 'Zonsondergang', got {text}"
