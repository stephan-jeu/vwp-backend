from __future__ import annotations

import os


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
OUT_DIR = os.path.join(ROOT_DIR, "db", "sql")
OUT_PATH = os.path.join(OUT_DIR, "seed_gierzwaluw.sql")


def sql_escape(value: str) -> str:
    return value.replace("'", "''")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    family_name = "Zwaluw"
    species_name = "Gierzwaluw"
    function_name = "Nest"

    # Visit windows (year 2000)
    windows = [
        ("2000-06-01", "2000-06-15"),  # visit 1
        ("2000-06-15", "2000-06-30"),  # visit 2
        ("2000-07-01", "2000-07-15"),  # visit 3
    ]

    visits = 3
    visit_duration_hours = 2
    min_between_value = 10
    min_between_unit = "dagen"
    min_temperature_celsius = 13
    max_wind_force_bft = 4
    max_precipitation = "droog"

    # Start: 1.5 hours before sunset
    start_timing_reference = "sunset"
    start_time_relative_minutes = -90

    stmts: list[str] = []
    stmts.append("-- Seed generated for Gierzwaluw (family Zwaluw)")
    stmts.append("SET statement_timeout = 0;")

    # Family
    stmts.append(
        "INSERT INTO families (name, priority) VALUES ('%s', 5) ON CONFLICT (name) DO NOTHING;"
        % sql_escape(family_name)
    )

    # Species
    stmts.append(
        "INSERT INTO species (family_id, name, name_latin) "
        "VALUES ((SELECT id FROM families WHERE name = '%s'), '%s', NULL) "
        "ON CONFLICT (name) DO NOTHING;"
        % (
            sql_escape(family_name),
            sql_escape(species_name),
        )
    )

    # Function
    stmts.append(
        "INSERT INTO functions (name) VALUES ('%s') ON CONFLICT (name) DO NOTHING;"
        % sql_escape(function_name)
    )
    # Ensure additional SMP functions exist
    for func in ("SMP Voorverkenning", "SMP Nest"):
        stmts.append(
            "INSERT INTO functions (name) VALUES ('%s') ON CONFLICT (name) DO NOTHING;"
            % sql_escape(func)
        )

    # Protocol (no period_from/period_to; use windows below)
    protocol_cols = (
        "species_id, function_id, visits, visit_duration_hours, "
        "min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, "
        "start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, "
        "min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, "
        "visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit"
    )
    protocol_vals = (
        f"(SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = '{sql_escape(family_name)}' AND s.name = '{sql_escape(species_name)}'), "
        f"(SELECT id FROM functions WHERE name = '{sql_escape(function_name)}'), "
        f"{visits}, {visit_duration_hours}, "
        f"{min_between_value}, '{sql_escape(min_between_unit)}', "
        f"'{sql_escape(start_timing_reference)}', {start_time_relative_minutes}, "
        "NULL, NULL, NULL, NULL, "
        f"{min_temperature_celsius}, {max_wind_force_bft}, '{sql_escape(max_precipitation)}', "
        "NULL, NULL, NULL, false, false, false, false, NULL"
    )
    stmts.append(
        "INSERT INTO protocols (" + protocol_cols + ") VALUES (" + protocol_vals + ");"
    )

    # Insert visit windows (1..3)
    values_rows = [
        f"(1, DATE '{windows[0][0]}', DATE '{windows[0][1]}', true, NULL)",
        f"(2, DATE '{windows[1][0]}', DATE '{windows[1][1]}', true, NULL)",
        f"(3, DATE '{windows[2][0]}', DATE '{windows[2][1]}', true, NULL)",
    ]
    stmts.append(
        "INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)\n"
        + "SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label\n"
        + "FROM (VALUES\n  "
        + ",\n  ".join(values_rows)
        + "\n) AS v(visit_index, window_from, window_to, required, label),\n"
        + "LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = '"
        + sql_escape(family_name)
        + "' AND s.name = '"
        + sql_escape(species_name)
        + "') AND function_id = (SELECT id FROM functions WHERE name = '"
        + sql_escape(function_name)
        + "') ORDER BY id DESC LIMIT 1) AS p(id);"
    )

    # ------------------------------------------------------------------
    # SMP Voorverkenning for Gierzwaluw, Huiszwaluw, Boerenzwaluw
    # ------------------------------------------------------------------
    for sp in ("Gierzwaluw", "Huiszwaluw", "Boerenzwaluw"):
        # Ensure species exists (latin NULL)
        stmts.append(
            "INSERT INTO species (family_id, name, name_latin) "
            "VALUES ((SELECT id FROM families WHERE name = '%s'), '%s', NULL) "
            "ON CONFLICT (name) DO NOTHING;" % (sql_escape(family_name), sql_escape(sp))
        )
        # Protocol: 1 visit, duration 2h, 1.5h before sunset, wind<=4, precip droog
        stmts.append(
            "INSERT INTO protocols ("
            + protocol_cols
            + ") VALUES ("
            + (
                f"(SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = '{sql_escape(family_name)}' AND s.name = '{sql_escape(sp)}'), "
                f"(SELECT id FROM functions WHERE name = '{sql_escape('SMP Voorverkenning')}'), "
                f"1, 2, NULL, NULL, '{sql_escape(start_timing_reference)}', {start_time_relative_minutes}, "
                "NULL, NULL, NULL, NULL, NULL, 4, 'droog', 'Temperatuur afhankelijk per week', NULL, NULL, false, false, false, false, NULL"
            )
            + ");"
        )
        # Single window: 25-31 May (year 2000)
        stmts.append(
            "INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)\n"
            + "SELECT p.id, 1, DATE '2000-05-25', DATE '2000-05-31', true, NULL\n"
            + "FROM LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = '"
            + sql_escape(family_name)
            + "' AND s.name = '"
            + sql_escape(sp)
            + "') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Voorverkenning') ORDER BY id DESC LIMIT 1) AS p(id);"
        )

    # ------------------------------------------------------------------
    # SMP Nest for Gierzwaluw (2 visits with specific windows)
    # ------------------------------------------------------------------
    stmts.append(
        "INSERT INTO protocols ("
        + protocol_cols
        + ") VALUES ("
        + (
            f"(SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = '{sql_escape(family_name)}' AND s.name = '{sql_escape('Gierzwaluw')}'), "
            f"(SELECT id FROM functions WHERE name = '{sql_escape('SMP Nest')}'), "
            f"2, 2, 10, 'dagen', '{sql_escape(start_timing_reference)}', {start_time_relative_minutes}, "
            "NULL, NULL, NULL, NULL, NULL, 4, 'droog', 'Temperatuur afhankelijk per week', NULL, NULL, false, false, false, false, NULL"
        )
        + ");"
    )
    smp_rows = [
        "(1, DATE '2000-06-08', DATE '2000-06-30', true, NULL)",
        "(2, DATE '2000-07-01', DATE '2000-07-15', true, NULL)",
    ]
    stmts.append(
        "INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)\n"
        + "SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label\n"
        + "FROM (VALUES\n  "
        + ",\n  ".join(smp_rows)
        + "\n) AS v(visit_index, window_from, window_to, required, label),\n"
        + "LATERAL (SELECT id FROM protocols WHERE species_id = (SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = '"
        + sql_escape(family_name)
        + "' AND s.name = 'Gierzwaluw') AND function_id = (SELECT id FROM functions WHERE name = 'SMP Nest') ORDER BY id DESC LIMIT 1) AS p(id);"
    )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(stmts) + "\n")

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
