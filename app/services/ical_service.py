from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import icalendar

from app.models.visit import Visit

_TRAVEL_MINUTES = 120
_AMS = ZoneInfo("Europe/Amsterdam")


def _compute_location(visit: Visit) -> str | None:
    cluster = visit.cluster
    if cluster is None:
        return None

    if cluster.lat is not None and cluster.lon is not None:
        return f"{cluster.lat},{cluster.lon}"

    parts = [cluster.address]
    loc = cluster.location
    if not loc and cluster.project:
        loc = cluster.project.location
    if loc:
        parts.append(loc)

    return ", ".join(p for p in parts if p) or None


def _parse_activity_minutes(start_time_text: str | None) -> int:
    """Parse Dutch duration expressions and return total minutes including travel."""
    if not start_time_text:
        return _TRAVEL_MINUTES

    text = start_time_text.lower()

    if "anderhalf" in text:
        return _TRAVEL_MINUTES + 90

    match = re.search(r"(\d+(?:[.,]\d+)?)\s*uur", text)
    if match:
        hours = float(match.group(1).replace(",", "."))
        return _TRAVEL_MINUTES + int(hours * 60)

    match = re.search(r"(\d+)\s*min", text)
    if match:
        return _TRAVEL_MINUTES + int(match.group(1))

    return _TRAVEL_MINUTES


def _compute_summary(visit: Visit) -> str:
    project_code = visit.cluster.project.code if visit.cluster and visit.cluster.project else "?"
    cluster_number = visit.cluster.cluster_number if visit.cluster else "?"
    visit_nr = visit.visit_nr if visit.visit_nr is not None else "?"
    return f"{project_code} C{cluster_number} Bezoek {visit_nr}"


def _compute_description(visit: Visit) -> str:
    lines = []

    if visit.cluster and visit.cluster.project:
        lines.append(f"Project: {visit.cluster.project.code}")
    if visit.cluster:
        lines.append(f"Cluster: C{visit.cluster.cluster_number}")
        lines.append(f"Adres: {visit.cluster.address}")
    if visit.functions:
        lines.append(f"Activiteit: {', '.join(f.name for f in visit.functions)}")
    if visit.species:
        lines.append(f"Soorten: {', '.join(s.name for s in visit.species)}")
    if visit.researchers:
        names = [r.full_name for r in visit.researchers if r.full_name]
        if names:
            lines.append(f"Onderzoekers: {', '.join(names)}")
    if visit.part_of_day:
        lines.append(f"Dagdeel: {visit.part_of_day}")
    if visit.start_time_text:
        lines.append(f"Starttijd: {visit.start_time_text}")
    if visit.duration:
        hours = visit.duration / 60
        lines.append(f"Duur: {hours:g} uur")
    weather_parts = []
    if visit.min_temperature_celsius is not None:
        weather_parts.append(f"min {visit.min_temperature_celsius} °C")
    if visit.max_wind_force_bft is not None:
        weather_parts.append(f"max wind {visit.max_wind_force_bft} Bft")
    if visit.max_precipitation:
        weather_parts.append(f"max neerslag {visit.max_precipitation}")
    if weather_parts:
        lines.append(f"Weercondities: {', '.join(weather_parts)}")
    if visit.cluster and visit.cluster.project and visit.cluster.project.google_drive_folder:
        lines.append(f"Project folder: {visit.cluster.project.google_drive_folder}")
    if visit.remarks_field:
        lines.append(f"Opmerkingen veld: {visit.remarks_field}")
    if visit.remarks_planning:
        lines.append(f"Opmerkingen planning: {visit.remarks_planning}")

    return "\n".join(lines)


def _build_event(visit: Visit, event_date: date) -> icalendar.Event:
    event = icalendar.Event()
    event.add("uid", f"visit-{visit.id}@veldwerkplanning")
    event.add("summary", _compute_summary(visit))

    dtstart = datetime(event_date.year, event_date.month, event_date.day, 8, 0, 0, tzinfo=_AMS)

    if visit.duration:
        duration_minutes = _TRAVEL_MINUTES + visit.duration
    else:
        duration_minutes = _parse_activity_minutes(visit.start_time_text)

    event.add("dtstart", dtstart)
    event.add("dtend", dtstart + timedelta(minutes=duration_minutes))

    location = _compute_location(visit)
    if location:
        event.add("location", location)

    description = _compute_description(visit)
    if description:
        event.add("description", description)

    return event


def _make_calendar() -> icalendar.Calendar:
    cal = icalendar.Calendar()
    cal.add("prodid", "-//Veldwerkplanning//NL")
    cal.add("version", "2.0")
    cal.add("method", "PUBLISH")
    return cal


def _valid_weekdays(visit: Visit, week_monday: date) -> list[date]:
    """Return the Mon–Fri days in the week that fall within the visit's from/to window."""
    days = []
    for offset in range(5):
        candidate = week_monday + timedelta(days=offset)
        if visit.from_date and candidate < visit.from_date:
            continue
        if visit.to_date and candidate > visit.to_date:
            continue
        days.append(candidate)
    return days or [week_monday]


def _assign_week_dates(visits: list[Visit], week_monday: date) -> dict[int, date]:
    """Spread visits across the week, one per day where possible.

    Visits with fewer valid days are assigned first (most-constrained first),
    so that a visit only valid on Wednesday isn't crowded out by an unconstrained one.
    """
    valid_per_visit = [(v, _valid_weekdays(v, week_monday)) for v in visits]
    valid_per_visit.sort(key=lambda x: len(x[1]))

    used: set[date] = set()
    result: dict[int, date] = {}
    for visit, valid_days in valid_per_visit:
        chosen = next((d for d in valid_days if d not in used), valid_days[0])
        used.add(chosen)
        result[visit.id] = chosen
    return result


def build_visit_ical(visit: Visit) -> bytes:
    from core.settings import get_settings

    settings = get_settings()

    if settings.feature_daily_planning:
        event_date = visit.planned_date
    else:
        year = date.today().year
        week_monday = date.fromisocalendar(year, visit.planned_week, 1)  # type: ignore[arg-type]
        event_date = _valid_weekdays(visit, week_monday)[0]

    if event_date is None:
        event_date = date.today()

    cal = _make_calendar()
    cal.add_component(_build_event(visit, event_date))
    return cal.to_ical()


def build_week_ical(visits: list[Visit], week: int, year: int) -> bytes:
    from core.settings import get_settings

    settings = get_settings()
    feature_daily_planning = settings.feature_daily_planning
    week_monday = date.fromisocalendar(year, week, 1)

    cal = _make_calendar()

    if feature_daily_planning:
        for visit in visits:
            if visit.planned_date is None:
                continue
            cal.add_component(_build_event(visit, visit.planned_date))
    else:
        date_assignments = _assign_week_dates(visits, week_monday)
        for visit in visits:
            cal.add_component(_build_event(visit, date_assignments[visit.id]))

    return cal.to_ical()
