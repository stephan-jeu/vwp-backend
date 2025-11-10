### Functional overview: how visits are generated

- **Input selection**

  - Take the selected `species_ids` × `function_ids`.
  - Load all matching `Protocol` records with their `visit_windows`.

- **Organize by visit index**

  - Windows are processed per protocol and `visit_index` but bucketing is greedy across all windows (not strictly per-index batches).

- **Compute per-protocol attributes (per index)**

  - Shift each window to the current year.
  - Do not auto-shift by `min_period_between_visits`; explicit windows define spacing. Sequencing gaps are respected when placing visit_index > 1 in buckets.
  - Determine allowed part(s) of day as a set:
    - Hard constraints: `requires_morning_visit` → {"Ochtend"}, `requires_evening_visit` → {"Avond"}.
    - Timing rules:
      - SUNSET→SUNRISE or SUNSET_TO_SUNRISE → {"Avond","Ochtend"}.
      - SUNSET → {"Avond"}, SUNRISE → {"Ochtend"}, DAYTIME → {"Dag"}.
      - ABSOLUTE_TIME → {"Avond","Ochtend"} (actual chosen part is decided later).
    - Unknowns remain None (treated permissively when intersecting).

- **Bucket compatible protocols per index**

  - Greedy "tightest-first" placement over all protocol windows.
  - A candidate can join a bucket only if:
    - **Compatibility** via `_allow_together(a,b)` holds against all bucket protocols.
    - The intersected window is non-empty and at least `MIN_EFFECTIVE_WINDOW_DAYS` long (env, default 14).
    - The intersected part-of-day options are None or non-empty.
    - For `visit_index > 1`, the start respects sequencing vs the previous planned occurrence or the window gap.
  - For each bucket:
    - The bucket window is the intersection across its protocols.
    - Choose the bucket part-of-day from the intersected set with preference: Morning > Evening > Day.

- **Create combined visits (per bucket)**

  - Create one `Visit` with:
    - `from_date`/`to_date`: the bucket’s intersected window.
    - `part_of_day`: the chosen bucket value (fallback to the first derivable value across protocols if absent).
    - `start_time_text`: derived from `part_of_day` and relative minutes:
      - For Morning: subtract the longest duration from the earliest end-relative minutes if available; else generic "Zonsopkomst"/relative form.
      - For Evening: prefer the earliest start-relative minutes across protocols; else earliest end-relative minutes; else generic "Zonsondergang"/relative form.
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

- **Completion pass**

  - Ensure each protocol has at least one planned visit per identical window range.
  - Try attaching missing occurrences to an existing visit when:
    - The visit window overlaps the protocol window by at least `MIN_EFFECTIVE_WINDOW_DAYS`.
    - The visit’s chosen part is allowed for the protocol’s parts.
    - All existing visit protocols are compatible via `_allow_together`.
  - Otherwise, create a new dedicated visit within the protocol window (respecting sequencing gaps).
  - Re-coalesce after additions (compatibility-aware, see below).

- **Part-of-day assignment and splitting**

  - Pre-split: attempt to set at least one Morning/Evening per protocol if required, when allowed by the entry’s intersected parts.
  - Split pass: if not satisfiable by assignment alone, create a sibling visit with the required part-of-day and move required and compatible companions there (same-species first, then flexible compatibles).
  - Re-coalesce again afterwards (compatibility-aware).

- **Fallbacks**

  - If protocols don’t overlap in time, or violate the compatibility rules, they produce separate visits.

- **Extensibility hooks (in place)**
  - `_allow_together(a,b)`: central compatibility hook.
    - SMP rules: SMP protocols only combine with other SMP of the same family. No cross-family exceptions for SMP and never mix SMP with non-SMP.
    - Non‑SMP rules: allow same-family (by id or normalized name) and a curated cross-family allowlist (currently `{Vleermuis, Zwaluw}`).
  - `_apply_custom_recipe_if_any(protos, visit_index)`: placeholder to impose custom ordered combinations for specific family/function sets (e.g., B1, then B2+C1, then C2).

- **Coalescing behavior**

  - Entries with identical `(from_date, to_date, part_of_day)` are merged only if the union of protocol sets remains compatible under `_allow_together`. Otherwise they stay as separate entries for the same key.

- **Per-protocol occurrence indexing**

  - For identical windows, occurrences per protocol are assigned stable indices in chronological order and used to render `remarks_field` as lines like `Function: SpeciesAbbr (1/2)`.

- **Environment and debug**

  - `MIN_EFFECTIVE_WINDOW_DAYS` (default 14) controls the minimum intersected window length when combining.
  - `VISIT_GEN_DEBUG` enables detailed logging to the application logger.
