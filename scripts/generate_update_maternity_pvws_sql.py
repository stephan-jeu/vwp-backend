from __future__ import annotations

import os

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, os.pardir))
OUT_DIR = os.path.join(ROOT_DIR, "db", "sql")
OUT_PATH = os.path.join(OUT_DIR, "update_maternity_pvws.sql")


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    sql = (
        """
-- Update protocol_visit_windows for protocols requiring a maternity-period visit
-- Rule:
--  - For each protocol p where requires_maternity_period_visit = true:
--      * Find the species' Kraamverblijfplaats protocol (same species)
--      * Use its first window (min visit_index) as the maternity period
--      * Set p's first window (visit_index = 1) to exactly that period
--      * Set p's second window (visit_index = 2), if present, to start at the end of that period
--        (window_from = kraam.window_to), keeping its existing window_to

SET statement_timeout = 0;

WITH kraam_func AS (
  SELECT id FROM functions WHERE name = 'Kraamverblijfplaats' LIMIT 1
),

-- Target protocols that require maternity-period visit and have a kraam protocol in the same species
targets AS (
  SELECT p.id AS protocol_id, p.species_id, kp.id AS kraam_protocol_id
  FROM protocols p
  JOIN kraam_func kf ON TRUE
  JOIN protocols kp ON kp.species_id = p.species_id AND kp.function_id = kf.id
  WHERE p.requires_maternity_period_visit = true
),

-- Determine the first (earliest index) kraam window per species
kraam_first AS (
  SELECT t.protocol_id, kvw.window_from AS kraam_from, kvw.window_to AS kraam_to
  FROM targets t
  JOIN LATERAL (
    SELECT kvw.window_from, kvw.window_to
    FROM protocol_visit_windows kvw
    WHERE kvw.protocol_id = t.kraam_protocol_id
    ORDER BY kvw.visit_index ASC
    LIMIT 1
  ) kvw ON TRUE
),

-- Update first visit window of target protocol to exactly the kraam maternity window
upd_first AS (
  UPDATE protocol_visit_windows pvw
  SET window_from = k.kraam_from,
      window_to   = k.kraam_to
  FROM kraam_first k
  WHERE pvw.protocol_id = k.protocol_id
    AND pvw.visit_index = 1
  RETURNING pvw.protocol_id
)

-- Update second visit window (if present) to start at the end of the maternity window
UPDATE protocol_visit_windows pvw
SET window_from = k.kraam_to
FROM kraam_first k
WHERE pvw.protocol_id = k.protocol_id
  AND pvw.visit_index = 2;
""".strip()
        + "\n"
    )

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(sql)

    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
