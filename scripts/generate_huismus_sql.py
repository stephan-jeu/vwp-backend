from __future__ import annotations

import os


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
OUT_DIR = os.path.join(ROOT_DIR, "db", "sql")
OUT_PATH = os.path.join(OUT_DIR, "seed_huismus.sql")


def sql_escape(value: str) -> str:
    """Escape single quotes for SQL literals.

    Args:
        value: The string value to escape.

    Returns:
        Escaped string safe to interpolate into single-quoted SQL literals.
    """

    return value.replace("'", "''")


def main() -> None:
    """Generate SQL seed statements for Huismus protocol.

    Creates `seed_huismus.sql` with idempotent inserts for:
    - family: Mus
    - species: Huismus (latin left NULL)
    - function: kraamverblijfplaats (assumed existing but inserted just-in-case)
    - protocol with the provided constraints
    """

    os.makedirs(OUT_DIR, exist_ok=True)

    family_name = "Mus"
    species_name = "Huismus"
    species_name_latin = None  # Unknown/not provided; nullable column in schema
    function_name = "kraamverblijfplaats"

    # Business rules provided:
    visits = 2
    min_between_value = 10
    min_between_unit = "days"
    # Set concrete dates using a convention year (2000)
    period_from_date = "2000-04-01"
    period_to_date = "2000-05-15"
    visit_duration_hours = 1
    visit_conditions_text = "Gunstige weeromstandigheden"
    # Weather / timing
    max_wind_force_bft = 4
    max_precipitation = "geen regen"
    start_timing_reference = "sunrise"
    start_time_relative_minutes = 60  # 1 hour after sunrise

    stmts: list[str] = []
    stmts.append("-- Seed generated for Huismus (family Mus)")
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

    # Protocol. Keep period dates NULL (see bats generator); preserve textual period in conditions.
    stmts.append(
        "INSERT INTO protocols ("  # columns
        "species_id, function_id, period_from, period_to, visits, visit_duration_hours, "
        "min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, "
        "start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, "
        "min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, "
        "visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action"  # noqa: E501
        ") VALUES ("  # values
        f"(SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = '{sql_escape(family_name)}' AND s.name = '{sql_escape(species_name)}'), "
        f"(SELECT id FROM functions WHERE name = '{sql_escape(function_name)}'), "
        f"'{period_from_date}', '{period_to_date}', "  # period_from, period_to
        f"{int(visits)}, {int(visit_duration_hours)}, "
        f"{int(min_between_value)}, '{sql_escape(min_between_unit)}', "
        f"'{sql_escape(start_timing_reference)}', {int(start_time_relative_minutes)}, "
        "NULL, NULL, "  # start_time_absolute_from/to
        "NULL, NULL, "  # end_timing_reference, end_time_relative_minutes
        "NULL, "  # min_temperature_celsius
        f"{int(max_wind_force_bft)}, '{sql_escape(max_precipitation)}', "
        "NULL, NULL, "  # start_time_condition, end_time_condition
        f"'{sql_escape(visit_conditions_text)}', "
        "false, false, false, false, NULL"
        ") ON CONFLICT DO NOTHING;"
    )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(stmts) + "\n")

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
