from __future__ import annotations

from datetime import date, timedelta

from app.models.visit import Visit


def _weekdays_in_window(visit: Visit, week_monday: date) -> list[date]:
    days = []
    for offset in range(5):
        candidate = week_monday + timedelta(days=offset)
        if visit.from_date and candidate < visit.from_date:
            continue
        if visit.to_date and candidate > visit.to_date:
            continue
        days.append(candidate)
    return days


def valid_weekdays(visit: Visit, week_monday: date) -> list[date]:
    """Return the Mon-Fri days in the week that fall within the visit's from/to window.

    Falls back to ``week_monday`` itself when no weekday satisfies the window, so
    callers that need to assign a concrete date always get one.
    """
    return _weekdays_in_window(visit, week_monday) or [week_monday]


def week_out_of_window(visit: Visit, week_monday: date) -> bool:
    """True when none of the week's weekdays fall inside the visit's from/to window."""
    return not _weekdays_in_window(visit, week_monday)
