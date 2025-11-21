## Introduction
This application is build for a dutch ecological consultancy agency called Habitus. The purpose is to generate and plan field visits to check for the presence of protected species. These visits have to follow specific protocols such as the Vleermuisprotocol 2021 that specify things like periods, time of day, number of visits, weather conditions etc. Other protocols are for example for Roofvogels, Huismus, Zwaluw etc. I have tried to encode these protocols into sqlalchmemy models (see @protocol.py and its relationships).
Most of the visits are generated using project cluster species/functions combinations. This is probably the most complex part of the application and you can find the logic in @visit_generation.py 

Another important module is actually planning visits for researchers. At the moment this is done on a weekly basis (although in the future it will probably be done specifying a period). See @visit_planning_selection.py  All researchers have certain weekly availability by day part: evening (usually around sunset), morning (usually a few hours before sunrise), daytime and flex (can be used for all three). They also have certain capabilities per species families, type of research like SMP (soort management plan), or facilites like a bike or a 'warmte beeld camera'. These are matched with the requirements of the visit, so that we can assign visits to the right researchers. We prioritize visits on criteria like visits that have a short time window left, for species that don't have a lot of available researchers. Once we have identified potential researchers for a visit we try to optimize to who we assign by looking at factors like travel time, the number of already assigned visits etc.

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






