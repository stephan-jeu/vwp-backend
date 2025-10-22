from __future__ import annotations

import os


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
OUT_DIR = os.path.join(ROOT_DIR, "db", "sql")
OUT_PATH = os.path.join(OUT_DIR, "seed_bats_smp.sql")


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


def to_sql_null_or_decimal_1(v):
    if v is None:
        return "NULL"
    return f"{float(v):.1f}"


def species_select(family_name: str, species_name: str) -> str:
    return (
        f"(SELECT s.id FROM species s JOIN families f ON s.family_id = f.id "
        f"WHERE f.name = '{sql_escape(family_name)}' AND s.name = '{sql_escape(species_name)}')"
    )


def function_select(function_name: str) -> str:
    return f"(SELECT id FROM functions WHERE name = '{sql_escape(function_name)}')"


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    family_name = "Vleermuis"

    stmts: list[str] = []
    stmts.append("-- Seed generated for bats SMP protocols")
    stmts.append("SET statement_timeout = 0;")

    # Ensure family exists
    stmts.append(
        "INSERT INTO families (name, priority) VALUES ('%s', 5) ON CONFLICT (name) DO NOTHING;"
        % sql_escape(family_name)
    )

    # Ensure species exist (latin unknown/NULL)
    for sp in ("laatvlieger", "gewone dwergvleermuis", "ruige dwergvleermuis"):
        stmts.append(
            "INSERT INTO species (family_id, name, name_latin) "
            "VALUES ((SELECT id FROM families WHERE name = '%s'), '%s', NULL) "
            "ON CONFLICT (name) DO NOTHING;" % (sql_escape(family_name), sql_escape(sp))
        )

    # Ensure functions exist
    for fn in (
        "SMP Groepsvorming kraamverblijf",
        "SMP Kraamverblijf",
        "SMP Massawinterverblijf",
        "SMP Paarverblijf",
    ):
        stmts.append(
            "INSERT INTO functions (name) VALUES ('%s') ON CONFLICT (name) DO NOTHING;"
            % sql_escape(fn)
        )

    # Common protocol column list (no period_from/period_to)
    protocol_cols = (
        "species_id, function_id, visits, visit_duration_hours, "
        "min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, "
        "start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, "
        "min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, "
        "visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit, special_follow_up_action"
    )

    # Helper to append a protocol insert and its windows
    def add_protocol_with_windows(
        species_name: str,
        function_name: str,
        visits: int,
        duration_hours: float | int | None,
        min_gap_value: int | None,
        min_gap_unit: str | None,
        start_ref: str | None,
        start_rel_minutes: int | None,
        min_temp: int | None,
        max_wind: int | None,
        max_precip: str | None,
        start_time_condition: str | None,
        windows: list[tuple[str, str]],
        special_note: str | None = None,
    ) -> None:
        vals = (
            f"{species_select(family_name, species_name)}, {function_select(function_name)}, "
            f"{to_sql_null_or_int(visits)}, {to_sql_null_or_decimal_1(duration_hours)}, "
            f"{to_sql_null_or_int(min_gap_value)}, {to_sql_null_or_str(min_gap_unit)}, "
            f"{to_sql_null_or_str(start_ref)}, {to_sql_null_or_int(start_rel_minutes)}, "
            "NULL, NULL, NULL, NULL, "
            f"{to_sql_null_or_int(min_temp)}, {to_sql_null_or_int(max_wind)}, {to_sql_null_or_str(max_precip)}, "
            f"{to_sql_null_or_str(start_time_condition)}, NULL, {to_sql_null_or_str(special_note)}, false, false, false, false, NULL"
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

    # 1) Laatvlieger — SMP Groepsvorming kraamverblijf
    add_protocol_with_windows(
        species_name="Laatvlieger",
        function_name="SMP Groepsvorming kraamverblijf",
        visits=2,
        duration_hours=3,
        min_gap_value=10,
        min_gap_unit="dagen",
        start_ref="sunset",
        start_rel_minutes=0,
        min_temp=12,
        max_wind=3,
        max_precip="droog",
        start_time_condition=None,
        windows=[("2000-04-15", "2000-05-15"), ("2000-04-15", "2000-05-15")],
    )

    # 2) Laatvlieger, Gewone dwergvleermuis — SMP Kraamverblijf (2 visits, v3/v4)
    for sp in ("laatvlieger", "gewone dwergvleermuis"):
        add_protocol_with_windows(
            species_name=sp,
            function_name="SMP Kraamverblijf",
            visits=2,
            duration_hours=2.5,
            min_gap_value=20,
            min_gap_unit="dagen",
            start_ref="sunset",
            start_rel_minutes=0,
            min_temp=12,
            max_wind=3,
            max_precip="droog",
            start_time_condition=None,
            windows=[("2000-05-15", "2000-06-15"), ("2000-06-16", "2000-07-15")],
        )

    # 3) Laatvlieger, Gewone dwergvleermuis — SMP Kraamverblijf (4 visits, v5..v8) start 2.5h before sunrise
    for sp in ("laatvlieger", "gewone dwergvleermuis"):
        add_protocol_with_windows(
            species_name=sp,
            function_name="SMP Kraamverblijf",
            visits=4,
            duration_hours=2.5,
            min_gap_value=12,
            min_gap_unit="dagen",
            start_ref="sunrise",
            start_rel_minutes=-150,
            min_temp=10,
            max_wind=3,
            max_precip="droog",
            start_time_condition=None,
            windows=[
                ("2000-05-15", "2000-05-31"),
                ("2000-06-01", "2000-06-30"),
                ("2000-06-01", "2000-06-30"),
                ("2000-07-01", "2000-07-15"),
            ],
        )

    # 4) Gewone dwergvleermuis — Massawinterverblijf (2 visits, 1-31 aug), start from 2h after sunset
    add_protocol_with_windows(
        species_name="gewone dwergvleermuis",
        function_name="SMP Massawinterverblijf",
        visits=2,
        duration_hours=3.5,
        min_gap_value=10,
        min_gap_unit="dagen",
        start_ref="sunset",
        start_rel_minutes=120,
        min_temp=15,
        max_wind=2,
        max_precip="droog",
        start_time_condition=None,
        windows=[("2000-08-01", "2000-08-31"), ("2000-08-01", "2000-08-31")],
    )

    # 5) Gewone dwergvleermuis, Ruige dwergvleermuis — Paarverblijf (1 visit, 1-30 sept), start from 3h after sunset
    for sp in ("gewone dwergvleermuis", "ruige dwergvleermuis"):
        add_protocol_with_windows(
            species_name=sp,
            function_name="SMP Paarverblijf",
            visits=1,
            duration_hours=2.5,
            min_gap_value=None,  # nvt
            min_gap_unit=None,
            start_ref="sunset",
            start_rel_minutes=180,
            min_temp=10,
            max_wind=3,
            max_precip="droog",
            start_time_condition=None,
            windows=[("2000-09-01", "2000-09-30")],
            special_note="Minimaal 10 dagen na laatste massawinterverblijfbezoek",
        )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(stmts) + "\n")

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
