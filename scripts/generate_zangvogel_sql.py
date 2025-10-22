from __future__ import annotations

import os


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
OUT_DIR = os.path.join(ROOT_DIR, "db", "sql")
OUT_PATH = os.path.join(OUT_DIR, "seed_zangvogel.sql")


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


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    family_name = "Zangvogel"
    species = [
        {"name": "Huismus", "name_latin": None},
        {"name": "Spreeuw", "name_latin": None},
    ]

    # Shared period used to build two identical visit windows
    period_from = "2000-04-01"
    period_to = "2000-05-15"

    stmts: list[str] = []
    stmts.append("-- Seed generated for family Zangvogel (Huismus, Spreeuw)")
    stmts.append("SET statement_timeout = 0;")

    # Family
    stmts.append(
        "INSERT INTO families (name, priority) VALUES ('%s', 5) ON CONFLICT (name) DO NOTHING;"
        % sql_escape(family_name)
    )

    # Species
    for sp in species:
        stmts.append(
            "INSERT INTO species (family_id, name, name_latin) "
            "VALUES ((SELECT id FROM families WHERE name = '%s'), '%s', %s) "
            "ON CONFLICT (name) DO NOTHING;"
            % (
                sql_escape(family_name),
                sql_escape(sp["name"]),
                to_sql_null_or_str(sp["name_latin"]) if sp["name_latin"] else "NULL",
            )
        )

    # Functions
    functions = ["Nest", "Nest en FL", "SMP Nest", "SMP Nest en FL"]
    for func in functions:
        stmts.append(
            "INSERT INTO functions (name) VALUES ('%s') ON CONFLICT (name) DO NOTHING;"
            % sql_escape(func)
        )

    def species_select(name: str) -> str:
        return (
            f"(SELECT s.id FROM species s JOIN families f ON s.family_id = f.id "
            f"WHERE f.name = '{sql_escape(family_name)}' AND s.name = '{sql_escape(name)}')"
        )

    def function_select(name: str) -> str:
        return f"(SELECT id FROM functions WHERE name = '{sql_escape(name)}')"

    def insert_protocol_and_windows(
        species_name: str,
        function_name: str,
        visits_count: int,
        visit_duration_hours: int,
        min_gap_value_in_days: int,
        min_gap_unit: str,
        min_temp_celsius: int,
        max_wind_bft: int,
        max_precip_text: str,
        start_timing_reference: str | None,
        start_time_relative_minutes: int | None,
        start_time_condition: str | None,
    ) -> None:
        # Insert protocol
        protocol_cols = (
            "species_id, function_id, visits, visit_duration_hours, "
            "min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, "
            "start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, "
            "min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, "
            "visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action"
        )
        protocol_vals = (
            f"{species_select(species_name)}, {function_select(function_name)}, "
            f"{to_sql_null_or_int(visits_count)}, {to_sql_null_or_int(visit_duration_hours)}, "
            f"{to_sql_null_or_int(min_gap_value_in_days)}, {to_sql_null_or_str(min_gap_unit)}, "
            f"{to_sql_null_or_str(start_timing_reference)}, {to_sql_null_or_int(start_time_relative_minutes)}, "
            f"NULL, NULL, NULL, NULL, "
            f"{to_sql_null_or_int(min_temp_celsius)}, {to_sql_null_or_int(max_wind_bft)}, {to_sql_null_or_str(max_precip_text)}, "
            f"{to_sql_null_or_str(start_time_condition)}, NULL, NULL, false, false, false, false, NULL"
        )
        stmts.append(
            "INSERT INTO protocols ("
            + protocol_cols
            + ") VALUES ("
            + protocol_vals
            + ");"
        )
        # Two identical windows for the period
        values_rows = [
            f"(1, DATE '{period_from}', DATE '{period_to}', true, NULL)",
            f"(2, DATE '{period_from}', DATE '{period_to}', true, NULL)",
        ]
        stmts.append(
            "INSERT INTO protocol_visit_windows (protocol_id, visit_index, window_from, window_to, required, label)\n"
            + "SELECT p.id, v.visit_index, v.window_from, v.window_to, v.required, v.label\n"
            + "FROM (VALUES\n  "
            + ",\n  ".join(values_rows)
            + "\n) AS v(visit_index, window_from, window_to, required, label),\n"
            + "LATERAL (SELECT id FROM protocols WHERE species_id = "
            + species_select(species_name)
            + " AND function_id = "
            + function_select(function_name)
            + " ORDER BY id DESC LIMIT 1) AS p(id);"
        )

    # Protocol 1: Huismus, Spreeuw -> Functie Nest
    for sp_name in ("Huismus", "Spreeuw"):
        insert_protocol_and_windows(
            species_name=sp_name,
            function_name="Nest",
            visits_count=2,
            visit_duration_hours=2,
            min_gap_value_in_days=10,
            min_gap_unit="dagen",
            min_temp_celsius=6,
            max_wind_bft=4,
            max_precip_text="droog",
            start_timing_reference="sunrise",
            start_time_relative_minutes=60,
            start_time_condition=None,
        )

    # Protocol 2: Huismus -> Functie Nest en FL (one function name)
    insert_protocol_and_windows(
        species_name="Huismus",
        function_name="Nest en FL",
        visits_count=2,
        visit_duration_hours=4,
        min_gap_value_in_days=10,
        min_gap_unit="dagen",
        min_temp_celsius=6,
        max_wind_bft=4,
        max_precip_text="droog",
        start_timing_reference=None,
        start_time_relative_minutes=None,
        start_time_condition="1-2 uur na zonsopkomst",
    )

    # Protocol 3: Huismus, Spreeuw -> Functie SMP Nest
    for sp_name in ("Huismus", "Spreeuw"):
        insert_protocol_and_windows(
            species_name=sp_name,
            function_name="SMP Nest",
            visits_count=2,
            visit_duration_hours=3,
            min_gap_value_in_days=14,
            min_gap_unit="dagen",
            min_temp_celsius=5,
            max_wind_bft=4,
            max_precip_text="droog",
            start_timing_reference=None,
            start_time_relative_minutes=None,
            start_time_condition="1-2 uur na zonsopkomst",
        )

    # Protocol 4: Huismus -> Functie SMP Nest en FL
    insert_protocol_and_windows(
        species_name="Huismus",
        function_name="SMP Nest en FL",
        visits_count=2,
        visit_duration_hours=4,
        min_gap_value_in_days=14,
        min_gap_unit="dagen",
        min_temp_celsius=5,
        max_wind_bft=4,
        max_precip_text="droog",
        start_timing_reference=None,
        start_time_relative_minutes=None,
        start_time_condition="1-2 uur na zonsopkomst",
    )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(stmts) + "\n")

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
