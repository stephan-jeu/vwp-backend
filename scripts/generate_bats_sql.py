from __future__ import annotations

import json
import os
import re


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

    # Helpers to convert textual Dutch month names into concrete dates (year 2000)
    month_map = {
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

    def parse_core_date(text: str | None) -> str | None:
        """Parse values like '1 dec', '15 mrt', or 'dec' into '2000-MM-DD'."""
        if not text:
            return None
        raw = str(text).strip().lower()
        # Pattern: 'DD mon'
        m = re.match(r"^(\d{1,2})\s+([a-z\u00e4\u00eb\u00ef\u00f6\u00fc]+)$", raw)
        if m:
            day = int(m.group(1))
            mon = m.group(2)
            month_num = month_map.get(mon)
            if month_num:
                return f"2000-{month_num:02d}-{day:02d}"
            return None
        # Pattern: only month name -> default to day 1
        if raw in month_map:
            return f"2000-{month_map[raw]:02d}-01"
        return None

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

        # Periods: parse textual into concrete dates using year 2000
        period_from = parse_core_date(row.get("period_from_core"))
        period_to = parse_core_date(row.get("period_to_core"))

        # Build window segments honoring year wrap; protocol_visit_windows requires from <= to
        window_segments: list[tuple[str, str]] = []
        if period_from and period_to:
            if period_from <= period_to:
                window_segments.append((period_from, period_to))
            else:
                # wrap-around: split into two segments
                window_segments.append((period_from, "2000-12-31"))
                window_segments.append(("2000-01-01", period_to))

        # Insert protocol and windows using a CTE to capture protocol id
        # Note: no period_from/period_to on protocols anymore
        protocol_insert_columns = (
            "species_id, function_id, visits, visit_duration_hours, "
            "min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, "
            "start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, "
            "min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, "
            "visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action"
        )

        species_select = (
            f"(SELECT s.id FROM species s JOIN families f ON s.family_id = f.id "
            f"WHERE f.name = '{sql_escape(family or '')}' AND s.name_latin = '{sql_escape(latin or '')}')"
        )
        function_select = (
            f"(SELECT id FROM functions WHERE name = '{sql_escape(func_name or '')}')"
        )

        protocol_values = (
            f"{species_select}, {function_select}, "
            f"{to_sql_null_or_int(visits)}, {to_sql_null_or_int(visit_duration_hours)}, "
            f"{to_sql_null_or_int(min_period_between_visits_value)}, {to_sql_null_or_str(min_period_between_visits_unit)}, "
            f"{to_sql_null_or_str(start_timing_reference)}, {to_sql_null_or_int(start_time_relative_minutes)}, "
            f"{to_sql_null_or_str(start_time_absolute_from)}, {to_sql_null_or_str(start_time_absolute_to)}, "
            f"{to_sql_null_or_str(end_timing_reference)}, {to_sql_null_or_int(end_time_relative_minutes)}, "
            f"{to_sql_null_or_int(min_temperature_celsius)}, {to_sql_null_or_int(max_wind_force_bft)}, {to_sql_null_or_str(max_precipitation)}, "
            f"{to_sql_null_or_str(start_time_condition)}, {to_sql_null_or_str(end_time_condition)}, {to_sql_null_or_str(visit_conditions_text)}, "
            f"{'true' if requires_morning_visit else 'false'}, {'true' if requires_evening_visit else 'false'}, {'true' if requires_june_visit else 'false'}, {'true' if requires_maternity_period_visit else 'false'}, {to_sql_null_or_str(special_follow_up_action)}"
        )

        # Insert Protocol row
        stmts.append(
            "INSERT INTO protocols ("
            + protocol_insert_columns
            + ") VALUES ("
            + protocol_values
            + ");"
        )

        # Insert protocol_visit_windows if we have segments and visits
        if window_segments and visits and int(visits) > 0:
            # Build values rows cycling segments
            values_rows: list[str] = []
            for i in range(int(visits)):
                seg = window_segments[i % len(window_segments)]
                # visit_index is 1-based
                values_rows.append(
                    "( %d, DATE '%s', DATE '%s', true, NULL )" % (i + 1, seg[0], seg[1])
                )
            # Insert windows for the most recently inserted protocol for this species/function
            stmts.append(
                "INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)\n"
                + "SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label\n"
                + "FROM (VALUES\n  "
                + ",\n  ".join(values_rows)
                + "\n) AS v(visit_index, window_from, window_to, required, label),\n"
                + "LATERAL (SELECT id FROM protocols WHERE species_id = "
                + species_select
                + " AND function_id = "
                + function_select
                + " ORDER BY id DESC LIMIT 1) AS p(id);"
            )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(stmts) + "\n")

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
