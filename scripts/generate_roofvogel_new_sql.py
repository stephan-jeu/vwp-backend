from __future__ import annotations

import os


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
OUT_DIR = os.path.join(ROOT_DIR, "db", "sql")
OUT_PATH = os.path.join(OUT_DIR, "seed_roofvogel.sql")


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

    family_name = "Roofvogel"
    function_name = "Nest"

    stmts: list[str] = []
    stmts.append("-- Seed generated for family Roofvogel protocols")
    stmts.append("SET statement_timeout = 0;")

    # Ensure family
    stmts.append(
        "INSERT INTO families (name, priority) VALUES ('%s', 5) ON CONFLICT (name) DO NOTHING;"
        % sql_escape(family_name)
    )

    # Ensure function
    stmts.append(
        "INSERT INTO functions (name) VALUES ('%s') ON CONFLICT (name) DO NOTHING;"
        % sql_escape(function_name)
    )

    # Ensure species
    for sp in (
        "Buizerd",
        "Sperwer",
        "Slechtvalk",
        "Havik",
        "Wespendief",
        "Boomvalk",
        "Ransuil",
    ):
        stmts.append(
            "INSERT INTO species (family_id, name, name_latin) "
            "VALUES ((SELECT id FROM families WHERE name = '%s'), '%s', NULL) "
            "ON CONFLICT (name) DO NOTHING;" % (sql_escape(family_name), sql_escape(sp))
        )

    # Common protocol columns (no period_from/to)
    protocol_cols = (
        "species_id, function_id, visits, visit_duration_hours, "
        "min_period_between_visits_value, min_period_between_visits_unit, start_timing_reference, start_time_relative_minutes, "
        "start_time_absolute_from, start_time_absolute_to, end_timing_reference, end_time_relative_minutes, "
        "min_temperature_celsius, max_wind_force_bft, max_precipitation, start_time_condition, end_time_condition, "
        "visit_conditions_text, requires_morning_visit, requires_evening_visit, requires_june_visit, requires_maternity_period_visit"
    )

    def add_protocol_with_windows(
        species_name: str,
        visits: int,
        duration_hours: float | int,
        min_gap_days: int,
        start_ref: str | None,
        start_rel_minutes: int | None,
        start_time_condition: str | None,
        min_temp_note: str | None,
        max_wind_bft: int,
        max_precip_text: str,
        researcher_note: str | None,
        windows: list[tuple[str, str]],
    ) -> None:
        visit_conditions_text = (
            "; ".join([p for p in [min_temp_note, researcher_note] if p]) or None
        )

        vals = (
            f"{species_select(family_name, species_name)}, {function_select(function_name)}, "
            f"{to_sql_null_or_int(visits)}, {float(duration_hours):.1f}, "
            f"{to_sql_null_or_int(min_gap_days)}, 'dagen', "
            f"{to_sql_null_or_str(start_ref)}, {to_sql_null_or_int(start_rel_minutes)}, "
            "NULL, NULL, NULL, NULL, "
            "NULL, "
            f"{to_sql_null_or_int(max_wind_bft)}, {to_sql_null_or_str(max_precip_text)}, "
            f"{to_sql_null_or_str(start_time_condition)}, NULL, {to_sql_null_or_str(visit_conditions_text)}, false, false, false, false, NULL"
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

    # Shared
    remark = "Bezoeken uitvoeren met WBC; periodiek afspelen geluid ransuil."
    no_frost = "Geen vrieskou"

    # Buizerd
    add_protocol_with_windows(
        species_name="Buizerd",
        visits=4,
        duration_hours=2,
        min_gap_days=10,
        start_ref=None,
        start_rel_minutes=None,
        start_time_condition="Overdag",
        min_temp_note=no_frost,
        max_wind_bft=3,
        max_precip_text="Droog",
        researcher_note=remark,
        windows=[
            ("2000-03-01", "2000-03-15"),
            ("2000-03-16", "2000-04-30"),
            ("2000-03-16", "2000-04-30"),
            ("2000-05-01", "2000-05-15"),
        ],
    )

    # Sperwer
    add_protocol_with_windows(
        species_name="Sperwer",
        visits=4,
        duration_hours=2,
        min_gap_days=10,
        start_ref=None,
        start_rel_minutes=None,
        start_time_condition="Overdag",
        min_temp_note=no_frost,
        max_wind_bft=3,
        max_precip_text="Droog",
        researcher_note=remark,
        windows=[
            ("2000-03-01", "2000-03-15"),
            ("2000-03-16", "2000-04-30"),
            ("2000-03-16", "2000-04-30"),
            ("2000-07-01", "2000-07-15"),
        ],
    )

    # Slechtvalk (min gap 20)
    add_protocol_with_windows(
        species_name="Slechtvalk",
        visits=4,
        duration_hours=2,
        min_gap_days=20,
        start_ref=None,
        start_rel_minutes=None,
        start_time_condition="Overdag",
        min_temp_note=no_frost,
        max_wind_bft=3,
        max_precip_text="Droog",
        researcher_note=remark,
        windows=[
            ("2000-02-01", "2000-03-15"),
            ("2000-02-01", "2000-03-15"),
            ("2000-03-16", "2000-04-30"),
            ("2000-06-01", "2000-06-30"),
        ],
    )

    # Havik
    add_protocol_with_windows(
        species_name="Havik",
        visits=4,
        duration_hours=2,
        min_gap_days=10,
        start_ref=None,
        start_rel_minutes=None,
        start_time_condition="Overdag",
        min_temp_note=no_frost,
        max_wind_bft=3,
        max_precip_text="Droog",
        researcher_note=remark,
        windows=[
            ("2000-03-01", "2000-03-15"),
            ("2000-03-16", "2000-04-30"),
            ("2000-03-16", "2000-04-30"),
            ("2000-06-01", "2000-06-30"),
        ],
    )

    # Wespendief (min gap 20)
    add_protocol_with_windows(
        species_name="Wespendief",
        visits=4,
        duration_hours=2,
        min_gap_days=20,
        start_ref=None,
        start_rel_minutes=None,
        start_time_condition="Overdag",
        min_temp_note=no_frost,
        max_wind_bft=3,
        max_precip_text="Droog",
        researcher_note=remark,
        windows=[
            ("2000-05-01", "2000-05-15"),
            ("2000-05-15", "2000-06-15"),
            ("2000-06-16", "2000-07-15"),
            ("2000-07-16", "2000-08-15"),
        ],
    )

    # Boomvalk (start 1h before sunset)
    add_protocol_with_windows(
        species_name="Boomvalk",
        visits=4,
        duration_hours=2,
        min_gap_days=20,
        start_ref="sunset",
        start_rel_minutes=-60,
        start_time_condition=None,
        min_temp_note=no_frost,
        max_wind_bft=3,
        max_precip_text="Droog",
        researcher_note=remark,
        windows=[
            ("2000-05-01", "2000-05-15"),
            ("2000-05-16", "2000-08-15"),
            ("2000-05-16", "2000-08-15"),
            ("2000-05-16", "2000-08-15"),
        ],
    )

    # Ransuil (start sunset)
    add_protocol_with_windows(
        species_name="Ransuil",
        visits=4,
        duration_hours=2,
        min_gap_days=20,
        start_ref="sunset",
        start_rel_minutes=0,
        start_time_condition=None,
        min_temp_note=no_frost,
        max_wind_bft=3,
        max_precip_text="Droog",
        researcher_note=remark,
        windows=[
            ("2000-02-15", "2000-03-15"),
            ("2000-03-16", "2000-04-15"),
            ("2000-05-15", "2000-06-15"),
            ("2000-06-16", "2000-07-15"),
        ],
    )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(stmts) + "\n")

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
