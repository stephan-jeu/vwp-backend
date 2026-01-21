pg_dump --column-inserts --data-only \
  --table=families \
  --table=species \
  --table=functions \
  --table=protocols \
  --table=protocol_visit_windows \
  --file=../db/sql/seeds_generated.sql \
  vwp