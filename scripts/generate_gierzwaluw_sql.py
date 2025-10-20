from __future__ import annotations

import os


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
OUT_DIR = os.path.join(ROOT_DIR, "db", "sql")
OUT_PATH = os.path.join(OUT_DIR, "seed_gierzwaluw.sql")


def sql_escape(value: str) -> str:
    """Escape single quotes for SQL literals.

    Args:
        value: The string value to escape.

    Returns:
        Escaped string safe to interpolate into single-quoted SQL literals.
    """

    return value.replace("'", "''")


def main() -> None:
    """Generate SQL seed statements for Gierzwaluw protocol.

    Creates `seed_gierzwaluw.sql` with idempotent inserts for:
    - family: Zwaluw
    - species: Gierzwaluw (latin left NULL)
    - function: kraamverblijfplaats (ensured)
    - protocol with the provided constraints
    """

    os.makedirs(OUT_DIR, exist_ok=True)

    family_name = "Zwaluw"
    species_name = "Gierzwaluw"
    species_name_latin = None  # Unknown/not provided; nullable column in schema
    function_name = "kraamverblijfplaats"

    # Business rules provided
    period_from_date = "2000-06-01"
    period_to_date = "2000-07-15"
    visits = 3
    min_between_value = 10
    min_between_unit = "days"
    requires_july_visit = True
    visit_duration_hours = 2
    # 1.5 hours before sunset -> -90 minutes relative to SUNSET
    start_timing_reference = "SUNSET"
    start_time_relative_minutes = -90
    max_precipitation = "geen regen"
    max_wind_force_bft = 3

    stmts: list[str] = []
    stmts.append("-- Seed generated for Gierzwaluw (family Zwaluw)")
    stmts.append("SET statement_timeout = 0;")

    # Family
    stmts.append(
        "INSERT INTO families (name, priority) VALUES ('%s', 5) ON CONFLICT (name) DO NOTHING;"
        % sql_escape(family_name)
    )

    # Species (latin left NULL intentionally)
    if species_name_latin is None:
        stmts.append(
            "INSERT INTO species (family_id, name, name_latin) "
            "VALUES ((SELECT id FROM families WHERE name = '%s'), '%s', NULL) "
            "ON CONFLICT (name) DO NOTHING;"
            % (
                sql_escape(family_name),
                sql_escape(species_name),
            )
        )
    else:
        stmts.append(
            "INSERT INTO species (family_id, name, name_latin) "
            "VALUES ((SELECT id FROM families WHERE name = '%s'), '%s', '%s') "
            "ON CONFLICT (name) DO NOTHING;"
            % (
                sql_escape(family_name),
                sql_escape(species_name),
                sql_escape(species_name_latin),
            )
        )

    # Function (ensure existence)
    stmts.append(
        "INSERT INTO functions (name) VALUES ('%s') ON CONFLICT (name) DO NOTHING;"
        % sql_escape(function_name)
    )

    # Protocol insert; include requires_july_visit flag
    stmts.append(
        "INSERT INTO protocols ("  # columns
        "species_id, function_id, period_from, period_to, visits, visit_duration_hours, "
        "min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, "
        "start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, "
        "min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, "
        "visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, requires_july_visit, special_follow_up_action"
        ") VALUES ("  # values
        f"(SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = '{sql_escape(family_name)}' AND s.name = '{sql_escape(species_name)}'), "
        f"(SELECT id FROM functions WHERE name = '{sql_escape(function_name)}'), "
        f"'{period_from_date}', '{period_to_date}', "
        f"{int(visits)}, {int(visit_duration_hours)}, "
        f"{int(min_between_value)}, '{sql_escape(min_between_unit)}', "
        f"'{sql_escape(start_timing_reference)}', {int(start_time_relative_minutes)}, "
        "NULL, NULL, "  # start_time_absolute_from/to
        "NULL, NULL, "  # end_timing_reference, end_time_relative_minutes
        "NULL, "  # min_temperature_celsius
        f"{int(max_wind_force_bft)}, '{sql_escape(max_precipitation)}', "
        "NULL, NULL, "  # start_time_condition, end_time_condition
        "NULL, "  # visit_conditions_text
        "false, false, false, false, "
        f"{'true' if requires_july_visit else 'false'}, "
        "NULL"
        ") ON CONFLICT DO NOTHING;"
    )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(stmts) + "\n")

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
