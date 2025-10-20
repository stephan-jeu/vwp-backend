from __future__ import annotations

import calendar
import os
import re
from typing import Any


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
OUT_DIR = os.path.join(ROOT_DIR, "db", "sql")
OUT_PATH = os.path.join(OUT_DIR, "seed_roofvogel.sql")


def sql_escape(value: str) -> str:
    return value.replace("'", "''")


MONTHS = {
    "jan": 1,
    "januari": 1,
    "feb": 2,
    "februari": 2,
    "mrt": 3,
    "maart": 3,
    "apr": 4,
    "april": 4,
    "mei": 5,
    "jun": 6,
    "juni": 6,
    "jul": 7,
    "juli": 7,
    "aug": 8,
    "augustus": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "okt": 10,
    "oktober": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def normalize_date_text(text: str) -> str:
    return (
        text.strip()
        .lower()
        .replace(".", "")
        .replace("\u00a0", " ")
        .replace("- ", " ")
        .replace("-", " ")
    )


def parse_date_to_2000(text: str) -> str:
    raw = normalize_date_text(text)
    # Handle 'eind <month>' = last day of month
    m = re.match(r"^(eind)\s+([a-z]+)$", raw)
    if m:
        mon = m.group(2)
        month_num = MONTHS.get(mon)
        if month_num:
            last_day = calendar.monthrange(2000, month_num)[1]
            return f"2000-{month_num:02d}-{last_day:02d}"
    # Handle '<day> <month>'
    m = re.match(r"^(\d{1,2})\s+([a-z]+)$", raw)
    if m:
        day = int(m.group(1))
        mon = m.group(2)
        month_num = MONTHS.get(mon)
        if month_num:
            return f"2000-{month_num:02d}-{day:02d}"
    # Handle '<month>' -> first day
    if raw in MONTHS:
        return f"2000-{MONTHS[raw]:02d}-01"
    # Fallback: raise
    raise ValueError(f"Unrecognized date text: {text}")


def to_sql_null_or_int(v: int | None) -> str:
    return "NULL" if v is None else str(int(v))


def to_sql_null_or_str(v: str | None) -> str:
    return "NULL" if v is None else f"'{sql_escape(v)}'"


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    family_name = "Roofvogel"

    # Structured specs derived from the CSV-like input
    # Each item may expand into one or more protocol entries via the "variants" list
    specs: list[dict[str, Any]] = [
        {
            "species": "Steenuil",
            "function": "Nest & rustplaats",
            "period_from": "1 februari",
            "period_to": "30 april",
            "weather": "Geen regen, < 4 Bft",
            "source": "Kennisdocument BIJ12 NGB-protocol",
            "notes": "Bezoeken uitvoeren met WBC; periodiek afspelen baltsroep steenuil.",
            # Split into two protocols per plan
            "variants": [
                {
                    "label": "avond - baltsroep",
                    "visits": 3,
                    "duration_hours": 2,
                    "start_ref": "SUNSET",
                    "start_offset_min": 30,  # half hour after sunset
                    "min_gap_days": None,
                    "conditions_extra": "in de avondschemer, vanaf een halfuur na zonsondergang, tot middernacht.",
                },
                {
                    "label": "overdag - sporen",
                    "visits": 1,
                    "duration_hours": 2,
                    "start_ref": None,
                    "start_offset_min": None,
                    "min_gap_days": None,
                    "conditions_extra": "In de ochtendschemer, van anderhalf uur voor zonsopkomst tot zonsopkomst.",
                },
            ],
            # Month-long span requirement stored as free text
            "min_gap_text": "Minimaal 1 maand tussen eerste en laatste bezoek",
        },
        {
            "species": "Buizerd",
            "function": "Nest & rustplaats",
            "visits": 4,
            "period_from": "1 maart",
            "period_to": "15 mei",
            "duration_hours": 2,
            "min_gap_days": 10,
            "time_text": "overdag (tussen zonsopkomst en zonsondergang)",
            "weather": "Geen regen, < 4 Bft, geen vrieskou",
            "source": "Kennisdocument BIJ12",
        },
        {
            "species": "Kerkuil",
            "function": "Nest & rustplaats",
            "visits": 3,  # evening/night visits
            "period_from": "1 februari",
            "period_to": "15 oktober",
            "duration_hours": 2,
            "min_gap_days": 20,  # choose strictest in (10) 20
            "time_text": "'s avonds en 's nachts",
            "weather": "Geen regen, < 4 Bft, geen vrieskou",
            "source": "Kennisdocument BIJ12",
            "variants": [
                {
                    "label": "avond/nacht",
                    "visits": 3,
                    "duration_hours": 2,
                    "start_ref": None,
                    "start_offset_min": None,
                    "min_gap_days": 20,
                    "conditions_extra": None,
                },
                {
                    "label": "overdag - sporen",
                    "visits": 1,
                    "duration_hours": 2,
                    "start_ref": None,
                    "start_offset_min": None,
                    "min_gap_days": 20,
                    "conditions_extra": "Bezoek overdag optioneel maar heeft voorkeur",
                },
            ],
        },
        {
            "species": "Wespendief",
            "function": "Nest",
            "visits": 4,
            "period_from": "15 mei",
            "period_to": "15 augustus",
            "duration_hours": 2,
            "min_gap_days": 20,
            "time_text": "Van enkele uren na zonsopkomst tot in de avond.",
            "weather": "Geen regen, < 4 Bft, geen vrieskou",
            "source": "Telrichtlijnen SOVON",
        },
        {
            "species": "Havik",
            "function": "Nest",
            "visits": 4,
            "period_from": "1 maart",
            "period_to": "15 mei",
            "duration_hours": 2,
            "min_gap_days": 10,
            "time_text": "overdag (tussen zonsopkomst en zonsondergang)",
            "weather": "Geen regen, < 4 Bft, geen vrieskou",
            "source": "Telrichtlijnen SOVON",
        },
        {
            "species": "Sperwer",
            "function": "Nest",
            "visits": 4,
            "period_from": "1 maart",
            "period_to": "15 juli",
            "duration_hours": 2,
            "min_gap_days": 10,
            "time_text": "overdag (tussen zonsopkomst en zonsondergang)",
            "weather": "Geen regen, < 4 Bft, geen vrieskou",
            "source": "Telrichtlijnen SOVON",
        },
        {
            "species": "Torenvalk",
            "function": "Nest",
            "visits": 4,
            "period_from": "1 maart",
            "period_to": "10 juli",
            "duration_hours": 2,
            "min_gap_days": 20,
            "time_text": "overdag (tussen zonsopkomst en zonsondergang)",
            "weather": "Geen regen, < 4 Bft, geen vrieskou",
            "source": "Telrichtlijnen SOVON",
        },
        {
            "species": "Boomvalk",
            "function": "Nest",
            "visits": 4,
            "period_from": "1 mei",
            "period_to": "31 augustus",
            "duration_hours": 2,
            "min_gap_days": 20,
            "time_text": "Gehele dag; roepactiviteit het hoogst in vroege ochtend en late avond en in schemer.",
            "weather": "Geen regen, < 4 Bft, geen vrieskou",
            "source": "Telrichtlijnen SOVON",
        },
        {
            "species": "Slechtvalk",
            "function": "Nest",
            "visits": 4,
            "period_from": "1 februari",
            "period_to": "15 juli",
            "duration_hours": 2,
            "min_gap_days": 20,
            "time_text": "overdag (tussen zonsopkomst en zonsondergang)",
            "weather": "Geen regen, < 4 Bft, geen vrieskou",
            "source": "Telrichtlijnen SOVON",
        },
        {
            "species": "Ransuil",
            "function": "Nest & rustplaats",
            "visits": 4,
            "period_from": "15 februari",
            "period_to": "15 juli",
            "duration_hours": 2,
            "min_gap_days": 20,
            "time_text": "In schemer en nacht. Meeste roepactiviteit van late avondschemer tot begin nacht.",
            "weather": "Geen regen, < 4 Bft, geen vrieskou",
            "source": "Telrichtlijnen SOVON",
        },
        {
            "species": "Ransuil",
            "function": "Roestplaats",
            "visits": 2,
            "period_from": "1 november",
            "period_to": "15 februari",
            "duration_hours": None,  # n.v.t.
            "min_gap_days": 20,
            "time_text": "overdag (tussen zonsopkomst en zonsondergang)",
            "weather": None,
            "source": "Telrichtlijnen SOVON",
        },
        # Multi-species identical protocol (Nestinventarisatie, bladeloos)
        *[
            {
                "species": s,
                "function": "Nestinventarisatie (bladerloze periode)",
                "visits": 1,
                "period_from": "1 december",
                "period_to": "eind februari",
                "duration_hours": None,
                "min_gap_days": None,
                "time_text": "Overdag",
                "weather": None,
                "source": "n.v.t.",
            }
            for s in ["Buizerd", "Havik", "Wespendief", "Sperwer"]
        ],
    ]

    stmts: list[str] = []
    stmts.append("-- Seed generated for Roofvogels (family Roofvogel)")
    stmts.append("SET statement_timeout = 0;")

    # Family
    stmts.append(
        "INSERT INTO families (name, priority) VALUES ('%s', 5) ON CONFLICT (name) DO NOTHING;"
        % sql_escape(family_name)
    )

    # Species and functions (ensure existence)
    seen_species: set[str] = set()
    seen_functions: set[str] = set()

    for item in specs:
        species = item["species"]
        function = item["function"]
        if species not in seen_species:
            seen_species.add(species)
            stmts.append(
                "INSERT INTO species (family_id, name, name_latin) "
                "VALUES ((SELECT id FROM families WHERE name = '%s'), '%s', NULL) "
                "ON CONFLICT (name) DO NOTHING;"
                % (sql_escape(family_name), sql_escape(species))
            )
        if function not in seen_functions:
            seen_functions.add(function)
            stmts.append(
                "INSERT INTO functions (name) VALUES ('%s') ON CONFLICT (name) DO NOTHING;"
                % sql_escape(function)
            )

    # Protocols
    def emit_protocol(
        species: str,
        function: str,
        period_from: str,
        period_to: str,
        visits: int,
        duration_hours: int | None,
        min_gap_days: int | None,
        start_ref: str | None,
        start_offset_min: int | None,
        weather: str | None,
        time_text: str | None,
        notes: str | None,
        source: str | None,
    ) -> None:
        pf = parse_date_to_2000(period_from)
        pt = parse_date_to_2000(period_to)
        visit_conditions_parts: list[str] = []
        if source:
            visit_conditions_parts.append(f"Bron: {source}")
        if notes:
            visit_conditions_parts.append(notes)
        if time_text:
            visit_conditions_parts.append(time_text)
        if weather:
            # structured: set columns when we can
            if "geen regen" in weather.lower():
                precip_sql = "'geen regen'"
            else:
                precip_sql = "NULL"
            max_wind = 3 if "< 4 bft" in weather.lower() else None
        else:
            precip_sql = "NULL"
            max_wind = None

        visit_conditions_text = (
            " | ".join(visit_conditions_parts) if visit_conditions_parts else None
        )
        unit_sql = "'days'" if min_gap_days is not None else "NULL"

        stmts.append(
            "INSERT INTO protocols ("  # columns
            "species_id, function_id, period_from, period_to, visits, visit_duration_hours, "
            "min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, "
            "start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, "
            "min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, "
            "visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action"
            ") VALUES ("  # values
            f"(SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = '{sql_escape(family_name)}' AND s.name = '{sql_escape(species)}'), "
            f"(SELECT id FROM functions WHERE name = '{sql_escape(function)}'), "
            f"'{pf}', '{pt}', "
            f"{int(visits)}, {to_sql_null_or_int(duration_hours)}, "
            f"{to_sql_null_or_int(min_gap_days)}, {unit_sql}, "
            f"{to_sql_null_or_str(start_ref)}, {to_sql_null_or_int(start_offset_min)}, "
            "NULL, NULL, "  # start_time_absolute_from/to
            "NULL, NULL, "  # end_timing_reference, end_time_relative_minutes
            "NULL, "  # min_temperature_celsius
            f"{to_sql_null_or_int(max_wind)}, "
            f"{precip_sql}, "
            "NULL, NULL, "  # start_time_condition, end_time_condition
            f"{to_sql_null_or_str(visit_conditions_text)}, "
            "false, false, false, false, NULL"
            ") ON CONFLICT DO NOTHING;"
        )

    for item in specs:
        species = item["species"]
        function = item["function"]
        period_from = item.get("period_from")
        period_to = item.get("period_to")
        weather = item.get("weather")
        time_text = item.get("time_text")
        notes = item.get("notes")
        source = item.get("source")

        variants = item.get("variants")
        if variants:
            for v in variants:
                emit_protocol(
                    species=species,
                    function=function,
                    period_from=period_from,
                    period_to=period_to,
                    visits=int(v.get("visits", item.get("visits", 1))),
                    duration_hours=v.get("duration_hours", item.get("duration_hours")),
                    min_gap_days=v.get("min_gap_days", item.get("min_gap_days")),
                    start_ref=v.get("start_ref"),
                    start_offset_min=v.get("start_offset_min"),
                    weather=weather,
                    time_text=(v.get("conditions_extra") or time_text),
                    notes=notes,
                    source=source,
                )
        else:
            emit_protocol(
                species=species,
                function=function,
                period_from=period_from,
                period_to=period_to,
                visits=int(item.get("visits", 1)),
                duration_hours=item.get("duration_hours"),
                min_gap_days=item.get("min_gap_days"),
                start_ref=None,
                start_offset_min=None,
                weather=weather,
                time_text=time_text,
                notes=notes,
                source=source,
            )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(stmts) + "\n")

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
