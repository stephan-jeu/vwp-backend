pg_dump --column-inserts --data-only --clean --if-exists \
  --table=families \
  --table=species \
  --table=functions \
  --table=protocols \
  --table=protocol_visit_windows \
  --file=backend/db/sql/seeds_generated.sql \
  vwp