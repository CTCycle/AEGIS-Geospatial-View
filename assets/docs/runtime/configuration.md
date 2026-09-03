# Configuration

Last updated: 2026-09-03

## Environment file

The primary runtime environment file is `settings/.env`. If it is missing,
startup creates it from `settings/.env.example`; an existing file is never
overwritten. The generated file remains local.

Common keys include:

- `AEGIS_DATA_DIR` (optional; defaults to `app/resources/runtime`)
- `SQLITE_LOCK_TIMEOUT` (positive seconds; defaults to `60`)
- `FASTAPI_HOST`
- `FASTAPI_PORT`
- `UI_HOST`
- `UI_PORT`
- `RELOAD`
- `BACKEND_LOGS_VISIBLE`
- `REALTIME_ALLOW_MISSING_ORIGIN` (default `false`; test-only exception for
  non-browser clients)
- `AEGIS_ALLOW_RESTRICTED_SOURCES` (default `false`; explicitly opts the
  deployment into public capabilities marked with the
  `restricted_usage_opt_in` runtime policy)

The SQLite database path is always derived as:

```text
<AEGIS_DATA_DIR or app/resources/runtime>/database.db
```

`SQLITE_LOCK_TIMEOUT` controls how long startup and the explicit launcher
initialization action wait for the adjacent SQLite migration lock. It does not
change SQL transaction timeouts or database durability settings.

## Structured configuration

`settings/configurations.json` supplies JSON blocks for Nominatim, geospatial
bounds, map defaults, job polling, chat defaults, Open-Meteo, Overpass,
RainViewer, and NASA GIBS request tuning. It intentionally contains no
database block. Database location and migration-lock settings come from the
environment only.

Model provider API keys are entered through Settings and stored as encrypted
database records. They are not database connection settings.

## Local profile

The source template is `settings/.env.example`. The Windows launcher uses the
configured hosts and ports for the local web workflow. `BACKEND_LOGS_VISIBLE`
controls whether backend logs use a visible terminal.
