from datetime import date
from typing import NamedTuple

class FakePattern(NamedTuple):
    start_date: date
    end_date: date
    max_mornings_per_week: int | None
    max_evenings_per_week: int | None
    schedule: dict

def test():
    # from app.services.visit_planning_selection import _compute_strict_daypart_caps
    patterns = [
        FakePattern(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            max_mornings_per_week=None,
            max_evenings_per_week=None,
            schedule={"monday": ["morning"], "tuesday": ["morning"], "wednesday": ["morning"], "thursday": ["morning"]}
        )
    ]
    
    # Just pasting the function's code to simulate
    from datetime import timedelta
    year = 2025
    week = 5
    w_start = date.fromisocalendar(year, week, 1)
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    
    morning_days = 0
    max_mornings = 2
    for i in range(7):
        day_date = w_start + timedelta(days=i)
        active = next((p for p in patterns if p.start_date <= day_date <= p.end_date), None)
        if not active: continue
        
        if active.max_mornings_per_week is not None:
            max_mornings = active.max_mornings_per_week
            
        slots = active.schedule.get(day_names[i], [])
        if "morning" in slots:
            morning_days += 1
            
    print(f"morning_days: {morning_days}, max_mornings: {max_mornings}, returned: {min(morning_days, max_mornings)}")

test()
