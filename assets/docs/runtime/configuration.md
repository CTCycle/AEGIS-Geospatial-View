# Configuration

Last updated: 2026-06-05

## Environment File

Primary runtime environment file: `settings/.env`

Common keys include:

- `FASTAPI_HOST`
- `FASTAPI_PORT`
- `UI_HOST`
- `UI_PORT`
- `RELOAD`
- `OPTIONAL_DEPENDENCIES`
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
- geospatial bounds and service tuning
- chat defaults
- provider-specific request tuning

Database mode and all database connection/security/performance settings come only
from `settings/.env` (or process environment variables). The JSON settings file
does not provide database configuration.

## Profile Differences

### Development Profile

Source template: `settings/.env.local.example`

- `OPTIONAL_DEPENDENCIES=true`
- intended for local web workflow

### Tauri Profile

Source template: `settings/.env.local.tauri.example`

- `OPTIONAL_DEPENDENCIES=false`
- intended for deterministic desktop packaging
