# Configuration

Last updated: 2026-08-02

## Environment File

Primary runtime environment file: `settings/.env`

Common keys include:

- `AEGIS_RUNTIME_DATA_DIR`
- `FASTAPI_HOST`
- `FASTAPI_PORT`
- `UI_HOST`
- `UI_PORT`
- `RELOAD`
- `BACKEND_LOGS_VISIBLE`
- `ALWAYS_REBUILD`
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

`settings/configurations.json` supplies the runtime JSON blocks for:

- Nominatim settings
- geospatial bounds
- map defaults
- job polling interval
- chat defaults
- Open-Meteo, Overpass, RainViewer, and NASA GIBS request tuning

Database mode and all database connection/security/performance settings come only
from `settings/.env` (or process environment variables). The JSON settings file
does not provide database configuration.

The JSON loader only maps the blocks used by `ConfigurationManager`; legacy
vector-sync and durable-job settings are not runtime controls.

Model provider API keys are not environment settings in the default flow. They
are entered through Settings and stored as encrypted credential records. The
selected provider/model and provider base URLs are persisted model settings;
DeepSeek, OpenCode Zen, and OpenCode Go use on-demand catalogs when requested.

`AEGIS_RUNTIME_DATA_DIR` optionally overrides the local runtime storage root used
for the embedded SQLite database. When unset, the embedded database defaults to
`%TEMP%/AEGIS Geospatial View/database.db` on Windows and
`<repo>/.runtime/database.db` elsewhere.

## Local Profile

Source template: `settings/.env.example`

- `BACKEND_LOGS_VISIBLE=true` shows backend logs in a dedicated terminal; when absent, the launcher defaults to `true`
- intended for the local web workflow
