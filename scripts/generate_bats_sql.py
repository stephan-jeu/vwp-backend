from __future__ import annotations

import json
import os
import re
from datetime import time


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
JSON_PATH = os.path.join(ROOT_DIR, "protocols", "bats.json")
OUT_DIR = os.path.join(ROOT_DIR, "db", "sql")
OUT_PATH = os.path.join(OUT_DIR, "seed_bats.sql")


def sql_escape(value: str) -> str:
    return value.replace("'", "''")


def parse_time(value: str | None) -> str | None:
    if not value:
        return None
    # Expect HH:MM
    if re.match(r"^\d{2}:\d{2}$", value):
        return f"{value}:00"
    return None


def to_sql_null_or_int(v):
    if v is None:
        return "NULL"
    return str(int(v))


def to_sql_null_or_str(v):
    if v is None:
        return "NULL"
    return f"'{sql_escape(str(v))}'"


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    families_seen: set[str] = set()
    species_seen: set[tuple[str, str]] = set()  # (latin, dutch)
    functions_seen: set[str] = set()

    stmts: list[str] = []
    stmts.append("-- Seed generated from protocols/bats.json")
    stmts.append("SET statement_timeout = 0;")

    # Families, species, and functions inserts (deduplicated)
    for row in data:
        family = row.get("family")
        latin = row.get("species_name")
        dutch = row.get("species_name_dutch")
        func_name = row.get("function")

        if family and family not in families_seen:
            families_seen.add(family)
            stmts.append(
                "INSERT INTO families (name, priority) VALUES ('%s', 5) ON CONFLICT (name) DO NOTHING;"
                % sql_escape(family)
            )

        if latin and dutch and (latin, dutch) not in species_seen:
            species_seen.add((latin, dutch))
            stmts.append(
                "INSERT INTO species (family_id, name, name_latin) "
                "VALUES ((SELECT id FROM families WHERE name = '%s'), '%s', '%s') "
                "ON CONFLICT (name) DO NOTHING;"
                % (
                    sql_escape(family or ""),
                    sql_escape(dutch),
                    sql_escape(latin),
                )
            )

        if func_name and func_name not in functions_seen:
            functions_seen.add(func_name)
            stmts.append(
                "INSERT INTO functions (name) VALUES ('%s') ON CONFLICT (name) DO NOTHING;"
                % sql_escape(func_name)
            )

    # Protocols
    for row in data:
        family = row.get("family")
        latin = row.get("species_name")
        func_name = row.get("function")

        visits = row.get("visits")
        visit_duration_hours = row.get("visit_duration_hours")
        min_period_between_visits_value = row.get("min_period_between_visits_value")
        min_period_between_visits_unit = row.get("min_period_between_visits_unit")
        start_timing_reference = row.get("start_timing_reference")
        start_time_relative_minutes = row.get("start_time_relative_minutes")
        start_time_absolute_from = parse_time(row.get("start_time_absolute_from"))
        start_time_absolute_to = parse_time(row.get("start_time_absolute_to"))
        end_timing_reference = row.get("end_timing_reference")
        end_time_relative_minutes = row.get("end_time_relative_minutes")
        min_temperature_celsius = row.get("min_temperature_celsius")
        max_wind_force_bft = row.get("max_wind_force_bft")
        max_precipitation = row.get("max_precipitation")
        start_time_condition = row.get("start_time_condition")
        end_time_condition = row.get("end_time_condition")
        visit_conditions_text = row.get("visit_conditions_text")
        requires_morning_visit = bool(row.get("requires_morning_visit"))
        requires_evening_visit = bool(row.get("requires_evening_visit"))
        requires_june_visit = bool(row.get("requires_june_visit"))
        requires_maternity_period_visit = bool(
            row.get("requires_maternity_period_visit")
        )
        special_follow_up_action = row.get("special_follow_up_action")

        # Periods in JSON are textual (e.g., '1 dec'); DB columns are DATE. Keep NULL and preserve text in conditions.
        period_from = None
        period_to = None
        # Append original textual periods into visit_conditions_text if present.
        extra_period_texts = []
        if row.get("period_from_core"):
            extra_period_texts.append(f"period_from_core: {row['period_from_core']}")
        if row.get("period_to_core"):
            extra_period_texts.append(f"period_to_core: {row['period_to_core']}")
        if extra_period_texts:
            visit_conditions_text = (
                (visit_conditions_text or "")
                + ("\n" if visit_conditions_text else "")
                + " | ".join(extra_period_texts)
            )

        stmts.append(
            "INSERT INTO protocols (species_id, function_id, period_from, period_to, visits, visit_duration_hours, "
            "min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, "
            "start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, "
            "min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, "
            "visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action) "
            "VALUES ("
            f"(SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = '{sql_escape(family or '')}' AND s.name_latin = '{sql_escape(latin or '')}'), "
            f"(SELECT id FROM functions WHERE name = '{sql_escape(func_name or '')}'), "
            f"{to_sql_null_or_str(period_from)}, {to_sql_null_or_str(period_to)}, "
            f"{to_sql_null_or_int(visits)}, {to_sql_null_or_int(visit_duration_hours)}, "
            f"{to_sql_null_or_int(min_period_between_visits_value)}, {to_sql_null_or_str(min_period_between_visits_unit)}, "
            f"{to_sql_null_or_str(start_timing_reference)}, {to_sql_null_or_int(start_time_relative_minutes)}, "
            f"{to_sql_null_or_str(start_time_absolute_from)}, {to_sql_null_or_str(start_time_absolute_to)}, "
            f"{to_sql_null_or_str(end_timing_reference)}, {to_sql_null_or_int(end_time_relative_minutes)}, "
            f"{to_sql_null_or_int(min_temperature_celsius)}, {to_sql_null_or_int(max_wind_force_bft)}, {to_sql_null_or_str(max_precipitation)}, "
            f"{to_sql_null_or_str(start_time_condition)}, {to_sql_null_or_str(end_time_condition)}, {to_sql_null_or_str(visit_conditions_text)}, "
            f"{'true' if requires_morning_visit else 'false'}, {'true' if requires_evening_visit else 'false'}, {'true' if requires_june_visit else 'false'}, {'true' if requires_maternity_period_visit else 'false'}, {to_sql_null_or_str(special_follow_up_action)}"
            ") ON CONFLICT DO NOTHING;"
        )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(stmts) + "\n")

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
