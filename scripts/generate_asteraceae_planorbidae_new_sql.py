from __future__ import annotations

import os


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
OUT_DIR = os.path.join(ROOT_DIR, "db", "sql")
OUT_PATH = os.path.join(OUT_DIR, "seed_asteraceae_planorbidae.sql")


def sql_escape(value: str) -> str:
    return value.replace("'", "''")


def to_sql_null_or_int(v):
    if v is None:
        return "NULL"
    return str(int(v))


def to_sql_null_or_str(v):
    if v is None:
        return "NULL"
    return f"'{sql_escape(str(v))}'"


def species_select(family_name: str, species_name: str) -> str:
    return (
        f"(SELECT s.id FROM species s JOIN families f ON s.family_id = f.id "
        f"WHERE f.name = '{sql_escape(family_name)}' AND s.name = '{sql_escape(species_name)}')"
    )


def function_select(function_name: str) -> str:
    return f"(SELECT id FROM functions WHERE name = '{sql_escape(function_name)}')"


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    # Families and species
    fam_asteraceae = "Asteraceae"
    fam_planorbidae = "Planorbidae"
    species_asteraceae = "Glad biggenkruid"
    species_planorbidae = "Platte schijfhoren"

    stmts: list[str] = []
    stmts.append(
        "-- Seed for Asteraceae (Glad biggenkruid) and Planorbidae (Platte schijfhoren)"
    )
    stmts.append("SET statement_timeout = 0;")

    # Ensure families
    for fam in (fam_asteraceae, fam_planorbidae):
        stmts.append(
            "INSERT INTO families (name, priority) VALUES ('%s', 5) ON CONFLICT (name) DO NOTHING;"
            % sql_escape(fam)
        )

    # Ensure species
    stmts.append(
        "INSERT INTO species (family_id, name, name_latin) "
        "VALUES ((SELECT id FROM families WHERE name = '%s'), '%s', NULL) "
        "ON CONFLICT (name) DO NOTHING;"
        % (sql_escape(fam_asteraceae), sql_escape(species_asteraceae))
    )
    stmts.append(
        "INSERT INTO species (family_id, name, name_latin) "
        "VALUES ((SELECT id FROM families WHERE name = '%s'), '%s', NULL) "
        "ON CONFLICT (name) DO NOTHING;"
        % (sql_escape(fam_planorbidae), sql_escape(species_planorbidae))
    )

    # Ensure functions
    for fn in ("Groeiplaats", "Leefgebied"):
        stmts.append(
            "INSERT INTO functions (name) VALUES ('%s') ON CONFLICT (name) DO NOTHING;"
            % sql_escape(fn)
        )

    # Common protocol columns
    protocol_cols = (
        "species_id, function_id, visits, visit_duration_hours, "
        "min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, "
        "start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, "
        "min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, "
        "visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit"
    )

    # Helper to add a protocol and its windows
    def add_protocol_with_windows(
        family_name: str,
        species_name: str,
        function_name: str,
        visits: int,
        duration_hours: float | int,
        min_gap_days: int | None,
        start_ref: str | None,
        start_rel_minutes: int | None,
        start_time_condition: str | None,
        temp_note: str | None,
        max_wind_bft: int | None,
        max_precip_text: str | None,
        windows: list[tuple[str, str]],
    ) -> None:
        gap_unit_sql = "'dagen'" if min_gap_days is not None else "NULL"
        vals = (
            f"{species_select(family_name, species_name)}, {function_select(function_name)}, "
            f"{to_sql_null_or_int(visits)}, {float(duration_hours):.1f}, "
            f"{to_sql_null_or_int(min_gap_days)}, {gap_unit_sql}, "
            f"{to_sql_null_or_str(start_ref)}, {to_sql_null_or_int(start_rel_minutes)}, "
            "NULL, NULL, NULL, NULL, "
            f"{to_sql_null_or_int(None)}, {to_sql_null_or_int(max_wind_bft)}, {to_sql_null_or_str(max_precip_text)}, "
            f"{to_sql_null_or_str(start_time_condition)}, NULL, {to_sql_null_or_str(temp_note)}, false, false, false, false, NULL"
        )
        stmts.append(
            "INSERT INTO protocols (" + protocol_cols + ") VALUES (" + vals + ");"
        )
        values_rows = [
            f"({i + 1}, DATE '{w[0]}', DATE '{w[1]}', true, NULL)"
            for i, w in enumerate(windows)
        ]
        stmts.append(
            "INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)\n"
            + "SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label\n"
            + "FROM (VALUES\n  "
            + ",\n  ".join(values_rows)
            + "\n) AS v(visit_index, window_from, window_to, required, label),\n"
            + "LATERAL (SELECT id FROM protocols WHERE species_id = "
            + species_select(family_name, species_name)
            + " AND function_id = "
            + function_select(function_name)
            + " ORDER BY id DESC LIMIT 1) AS p(id);"
        )

    # Glad biggenkruid — Groeiplaats
    add_protocol_with_windows(
        family_name=fam_asteraceae,
        species_name=species_asteraceae,
        function_name="Groeiplaats",
        visits=2,
        duration_hours=2,
        min_gap_days=21,
        start_ref=None,
        start_rel_minutes=None,
        start_time_condition="'s Ochtends",
        temp_note=None,
        max_wind_bft=None,
        max_precip_text=None,
        windows=[("2000-07-01", "2000-09-30"), ("2000-07-01", "2000-09-30")],
    )

    # Platte schijfhoren — Leefgebied
    add_protocol_with_windows(
        family_name=fam_planorbidae,
        species_name=species_planorbidae,
        function_name="Leefgebied",
        visits=1,
        duration_hours=2,
        min_gap_days=None,
        start_ref=None,
        start_rel_minutes=None,
        start_time_condition="Overdag",
        temp_note="Bij voorkeur niet na (hevige) regenbuien",
        max_wind_bft=None,
        max_precip_text=None,
        windows=[("2000-06-01", "2000-09-30")],
    )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(stmts) + "\n")

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
