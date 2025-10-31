from __future__ import annotations

import os


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
OUT_DIR = os.path.join(ROOT_DIR, "db", "sql")
OUT_PATH = os.path.join(OUT_DIR, "seed_rugstreeppad.sql")


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

    family_name = "Pad"
    species_name = "Rugstreeppad"

    stmts: list[str] = []
    stmts.append("-- Seed generated for Rugstreeppad (family Pad)")
    stmts.append("SET statement_timeout = 0;")

    # Ensure family
    stmts.append(
        "INSERT INTO families (name, priority) VALUES ('%s', 5) ON CONFLICT (name) DO NOTHING;"
        % sql_escape(family_name)
    )

    # Ensure species
    stmts.append(
        "INSERT INTO species (family_id, name, name_latin) "
        "VALUES ((SELECT id FROM families WHERE name = '%s'), '%s', NULL) "
        "ON CONFLICT (name) DO NOTHING;"
        % (sql_escape(family_name), sql_escape(species_name))
    )

    # Ensure functions
    functions = [
        "luisterbezoek",
        "platen neerleggen, eisnoeren/larven",
        "platen controleren, landhabitat",
    ]
    for fn in functions:
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

    def add_protocol_with_windows(
        function_name: str,
        visits: int,
        duration_hours: float | int,
        min_gap_days: int,
        start_ref: str | None,
        start_rel_minutes: int | None,
        start_time_condition: str | None,
        conditions_note: str | None,
        windows: list[tuple[str, str]],
    ) -> None:
        vals = (
            f"{species_select(family_name, species_name)}, {function_select(function_name)}, "
            f"{to_sql_null_or_int(visits)}, {float(duration_hours):.1f}, "
            f"{to_sql_null_or_int(min_gap_days)}, 'dagen', "
            f"{to_sql_null_or_str(start_ref)}, {to_sql_null_or_int(start_rel_minutes)}, "
            "NULL, NULL, NULL, NULL, "
            "NULL, NULL, 'droog', "
            f"{to_sql_null_or_str(start_time_condition)}, NULL, {to_sql_null_or_str(conditions_note)}, false, false, false, false, NULL"
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

    # 1) luisterbezoek — 3 visits, start 1h after sunset
    add_protocol_with_windows(
        function_name="luisterbezoek",
        visits=3,
        duration_hours=2,
        min_gap_days=7,
        start_ref="sunset",
        start_rel_minutes=60,
        start_time_condition=None,
        conditions_note="relatief warme avonden, bij voorkeur na regen of een weersomslag",
        windows=[
            ("2000-04-15", "2000-04-30"),
            ("2000-05-15", "2000-05-31"),
            ("2000-06-01", "2000-07-31"),
        ],
    )

    # 2) platen neerleggen, eisnoeren/larven — 1 visit, start 2h after sunset
    add_protocol_with_windows(
        function_name="platen neerleggen, eisnoeren/larven",
        visits=1,
        duration_hours=2,
        min_gap_days=7,
        start_ref="sunset",
        start_rel_minutes=120,
        start_time_condition=None,
        conditions_note=(
            "relatief warme avonden, bij voorkeur na regen of een weersomslag. "
            "Fijnmazig schepnet (RAVON-type) mee. Ook letten op koren en aanwezige individuen. "
            "Platen neerleggen in plangebied. Vuistregel circa 10 platen per 100m geschikt leefgebied."
        ),
        windows=[("2000-06-01", "2000-07-31")],
    )

    # 3) platen controleren, landhabitat — 4 visits, start 1h after sunset
    add_protocol_with_windows(
        function_name="platen controleren, landhabitat",
        visits=4,
        duration_hours=3,
        min_gap_days=7,
        start_ref="sunset",
        start_rel_minutes=60,
        start_time_condition=None,
        conditions_note="relatief warme avonden, bij voorkeur na regen of een weersomslag",
        windows=[("2000-07-01", "2000-08-31")] * 4,
    )

    with open(OUT_PATH, "w", encoding="utf-8") as out:
        out.write("\n".join(stmts) + "\n")

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
