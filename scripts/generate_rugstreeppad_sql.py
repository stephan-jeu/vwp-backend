from __future__ import annotations

import os


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
OUT_DIR = os.path.join(ROOT_DIR, "db", "sql")
OUT_PATH = os.path.join(OUT_DIR, "seed_rugstreeppad.sql")


def sql_escape(value: str) -> str:
    """Escape single quotes for SQL literals.

    Args:
        value: The string value to escape.

    Returns:
        Escaped string safe to interpolate into single-quoted SQL literals.
    """

    return value.replace("'", "''")


def to_sql_null_or_int(v: int | None) -> str:
    return "NULL" if v is None else str(int(v))


def to_sql_null_or_str(v: str | None) -> str:
    return "NULL" if v is None else f"'{sql_escape(v)}'"


def main() -> None:
    """Generate SQL seed statements for Rugstreeppad protocols.

    Creates `seed_rugstreeppad.sql` with idempotent inserts for:
    - family: Pad
    - species: Rugstreeppad (latin left NULL)
    - functions (5 variants)
    - protocols for each function as specified
    """

    os.makedirs(OUT_DIR, exist_ok=True)

    family_name = "Pad"
    species_name = "Rugstreeppad"
    species_name_latin = None  # Unknown/not provided; nullable column in schema

    stmts: list[str] = []
    stmts.append("-- Seed generated for Rugstreeppad (family Pad)")
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
            % (sql_escape(family_name), sql_escape(species_name))
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

    def protocol_insert(
        function_name: str,
        visits: int,
        start_timing_reference: str,
        start_time_relative_minutes: int,
        visit_duration_hours: int,
        period_from_date: str,
        period_to_date: str,
        min_between_value: int | None = None,
        min_between_unit: str | None = None,
        visit_conditions_text: str | None = None,
    ) -> None:
        # Ensure function exists
        stmts.append(
            "INSERT INTO functions (name) VALUES ('%s') ON CONFLICT (name) DO NOTHING;"
            % sql_escape(function_name)
        )

        # Insert protocol
        stmts.append(
            "INSERT INTO protocols ("  # columns
            "species_id, function_id, period_from, period_to, visits, visit_duration_hours, "
            "min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, "
            "start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, "
            "min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, "
            "visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action"
            ") VALUES ("  # values
            f"(SELECT s.id FROM species s JOIN families f ON s.family_id = f.id WHERE f.name = '{sql_escape(family_name)}' AND s.name = '{sql_escape(species_name)}'), "
            f"(SELECT id FROM functions WHERE name = '{sql_escape(function_name)}'), "
            f"'{period_from_date}', '{period_to_date}', "
            f"{int(visits)}, {int(visit_duration_hours)}, "
            f"{to_sql_null_or_int(min_between_value)}, {to_sql_null_or_str(min_between_unit)}, "
            f"'{sql_escape(start_timing_reference)}', {int(start_time_relative_minutes)}, "
            "NULL, NULL, "  # start_time_absolute_from/to
            "NULL, NULL, "  # end_timing_reference, end_time_relative_minutes
            "NULL, NULL, NULL, NULL, NULL, "  # min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition
            f"{to_sql_null_or_str(visit_conditions_text)}, "
            "false, false, false, false, NULL"
            ") ON CONFLICT DO NOTHING;"
        )

    # 1) luisterbezoek april
    protocol_insert(
        function_name="luisterbezoek april",
        visits=1,
        start_timing_reference="SUNSET",
        start_time_relative_minutes=60,
        visit_duration_hours=2,
        period_from_date="2000-04-15",
        period_to_date="2000-04-30",
        visit_conditions_text=(
            "relatief warme avonden, bij voorkeur na regen of een weersomslag"
        ),
    )

    # 2) luisterbezoek mei
    protocol_insert(
        function_name="luisterbezoek mei",
        visits=1,
        start_timing_reference="SUNSET",
        start_time_relative_minutes=60,
        visit_duration_hours=2,
        period_from_date="2000-05-15",
        period_to_date="2000-05-31",
        visit_conditions_text=(
            "relatief warme avonden, bij voorkeur na regen of een weersomslag"
        ),
    )

    # 3) luisterbezoek juni/juli
    protocol_insert(
        function_name="luisterbezoek juni/juli",
        visits=1,
        start_timing_reference="SUNSET",
        start_time_relative_minutes=60,
        visit_duration_hours=2,
        period_from_date="2000-06-01",
        period_to_date="2000-07-31",
        min_between_value=7,
        min_between_unit="days",
        visit_conditions_text=(
            "relatief warme avonden, bij voorkeur na regen of een weersomslag"
        ),
    )

    # 4) eisnoeren/larven + platen neerleggen
    protocol_insert(
        function_name="eisnoeren/larven + platen neerleggen",
        visits=1,
        start_timing_reference="SUNSET",
        start_time_relative_minutes=120,
        visit_duration_hours=2,
        period_from_date="2000-06-01",
        period_to_date="2000-07-31",
        min_between_value=7,
        min_between_unit="days",
        visit_conditions_text=None,
    )

    # 5) platen controleren, landhabitat
    protocol_insert(
        function_name="platen controleren, landhabitat",
        visits=4,
        start_timing_reference="SUNSET",
        start_time_relative_minutes=60,
        visit_duration_hours=3,
        period_from_date="2000-07-01",
        period_to_date="2000-08-31",
        min_between_value=7,
        min_between_unit="days",
        visit_conditions_text=(
            "relatief warme avonden, bij voorkeur na regen of een weersomslag"
        ),
    )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(stmts) + "\n")

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
