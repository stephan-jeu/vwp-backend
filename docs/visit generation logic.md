### Functional overview: how visits are generated

- **Input selection**

  - Take the selected `species_ids` × `function_ids`.
  - Load all matching `Protocol` records with their `visit_windows`.

- **Organize by visit index**

  - Group protocols by `visit_index` (1-based). We process indices in ascending order.

- **Compute per-protocol attributes (per index)**

  - Shift each window to the current year.
  - Apply an index offset in days: `(visit_index - 1) * max(min_period_between_visits)` across protocols in that index.
  - Determine allowed part(s) of day as a set:
    - Hard constraints: `requires_morning_visit` → {"Ochtend"}, `requires_evening_visit` → {"Avond"}.
    - Timing rules:
      - SUNSET→SUNRISE → {"Avond","Ochtend"}.
      - SUNSET → {"Avond"}, SUNRISE → {"Ochtend"}, DAYTIME → {"Dag"}.
      - ABSOLUTE_TIME → {"Ochtend"} if hour<12 else {"Avond"}.
    - Unknowns remain None (treated permissively when intersecting). Meaning that if by mistake a protocol does not evaluate to a part of day, it can be added to any.

- **Bucket compatible protocols per index**

  - Build an overlap graph from the shifted windows; find connected components (only items that time-overlap can combine).
  - Inside each component, greedily form buckets that satisfy:
    - **Family compatibility**: same family, or the specific cross-family exception `{'Vleermuis','Zwaluw'}`.
    - **Part-of-day compatibility**: non-empty intersection of allowed-part sets across the bucket.
  - For each bucket:
    - Compute the common date window as the intersection across windows; if empty, fall back to single-protocol visits within that bucket.
    - Choose the concrete part-of-day for the bucket from the intersected set with preference: Evening > Morning > Day.

- **Create combined visits (per bucket)**

  - Create one `Visit` with:
    - `from_date`/`to_date`: the bucket’s intersected window.
    - `part_of_day`: the chosen bucket value (fallback to a derived single value if absent).
    - `start_time`: earliest (minimum) derived minutes among protocols.
    - `start_time_text`: taken from the protocol with earliest minutes (re-derived as text).
    - Weather/conditions as “strictest” constraints:
      - `min_temperature_celsius`: maximum.
      - `max_wind_force_bft`: minimum.
      - `max_precipitation`: shortest non-empty text (proxy for most restrictive).
      - `duration`: maximum hours converted to minutes.
    - Remarks: whitelisted phrases extracted and joined with `" | "`.
    - Requires flags: any True across protocols becomes True.
    - Relations:
      - Functions: union of function ids in the bucket.
      - Species: union of species ids in the bucket.
  - Visits are numbered sequentially per cluster.

- **Fallbacks**

  - If protocols don’t overlap in time, or violate the compatibility rules, they produce separate visits.

- **Extensibility hooks (in place)**
  - `_allow_together(a,b)`: central compatibility hook (currently enforces same-family or the `Vleermuis`–`Zwaluw` exception).
  - `_apply_custom_recipe_if_any(protos, visit_index)`: placeholder to impose custom ordered combinations for specific family/function sets (e.g., B1, then B2+C1, then C2).
