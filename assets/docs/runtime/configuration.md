# Configuration

Last updated: 2026-07-12

## Environment File

Primary runtime environment file: `settings/.env`

Common keys include:

- `AEGIS_RUNTIME_DATA_DIR`
- `FASTAPI_HOST`
- `FASTAPI_PORT`
- `UI_HOST`
- `UI_PORT`
- `RELOAD`
- `OPTIONAL_DEPENDENCIES`
- `BACKEND_LOGS_VISIBLE`
- `EMBEDDED_DATABASE`
- `DATABASE_URL`
- `DATABASE_ENGINE`
- `DATABASE_HOST`
- `DATABASE_PORT`
- `DATABASE_NAME`
- `DATABASE_USERNAME`
- `DATABASE_PASSWORD`
- `DATABASE_SSL`
- `DATABASE_SSL_CA`
- `DATABASE_CONNECT_TIMEOUT`
- `DATABASE_INSERT_BATCH_SIZE`

## Structured Configuration

`settings/configurations.json` defines:

- job polling interval
- job backend selection
- durable-job requirement flag
- geospatial bounds and service tuning
- chat defaults
- provider-specific request tuning

Database mode and all database connection/security/performance settings come only
from `settings/.env` (or process environment variables). The JSON settings file
does not provide database configuration.

`AEGIS_RUNTIME_DATA_DIR` optionally overrides the local runtime storage root used
for the embedded SQLite database. When unset, the embedded database defaults to
`%TEMP%/AEGIS Geospatial View/database.db` on Windows and
`<repo>/.runtime/database.db` elsewhere.

## Local Profile

Source template: `settings/.env.example`

- `OPTIONAL_DEPENDENCIES=true`
- `BACKEND_LOGS_VISIBLE=true` shows backend logs in a dedicated terminal; when absent, the launcher defaults to `true`
- intended for the local web workflow
