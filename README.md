## Backend: Database & Alembic Migrations

### Environment variables (Settings)
Set these to point to your Postgres instance. Defaults (shown) are used if not set.

- **POSTGRES_USER**: database user (default: `postgres`)
- **POSTGRES_PASSWORD**: database password (default: `postgres`)
- **POSTGRES_HOST**: database host (default: `localhost`)
- **POSTGRES_PORT**: database port (default: `5432`)
- **POSTGRES_DB**: database name (default: `vwp`)
- **DB_ECHO**: SQLAlchemy echo logs (`true`/`false`, default: `false`)
- **DB_POOL_SIZE**: connection pool size (default: `5`)
- **DB_MAX_OVERFLOW**: pool max overflow (default: `10`)

These are read by `backend/core/settings.py` and form the async URL:
`postgresql+asyncpg://<POSTGRES_USER>:<POSTGRES_PASSWORD>@<POSTGRES_HOST>:<POSTGRES_PORT>/<POSTGRES_DB>`

### Alembic commands
Run all commands from the repository root so the `-c` path resolves correctly.

1) Upgrade to latest
```bash
alembic -c backend/alembic.ini upgrade head
```

2) Downgrade one revision
```bash
alembic -c backend/alembic.ini downgrade -1
```

3) Create a new revision (autogenerate against `Base.metadata`)
```bash
alembic -c backend/alembic.ini revision --autogenerate -m "your message"
```

4) Stamp the database (mark current state without running SQL)
```bash
alembic -c backend/alembic.ini stamp head
```

### Notes
- Alembic is configured for the async engine via `backend/alembic/env.py`.
- Initial migration lives in `backend/alembic/versions/20251013_01_initial.py`.
- Ensure the target database is reachable with the configured credentials before running migrations.


