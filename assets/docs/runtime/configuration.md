# Configuration

Last updated: 2026-08-18

## Environment File

Primary runtime environment file: `settings/.env`. If it is missing, startup
creates it from `settings/.env.example`; an existing file is never overwritten.
The generated file is ignored by Git and must remain local.

Common keys include:

- `AEGIS_RUNTIME_DATA_DIR`
- `FASTAPI_HOST`
- `FASTAPI_PORT`
- `UI_HOST`
- `UI_PORT`
- `RELOAD`
- `BACKEND_LOGS_VISIBLE`
- `REALTIME_ALLOW_MISSING_ORIGIN` (default `false`; test-only exception for
  non-browser clients)
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

The JSON loader maps the blocks used by `ConfigurationManager`; only typed
settings fields have runtime effect.

Model provider API keys are not environment settings in the default flow. They
are entered through Settings and stored as encrypted credential records. The
selected provider/model and provider base URLs are persisted model settings;
DeepSeek, OpenCode Zen, and OpenCode Go use on-demand catalogs when requested.

`AEGIS_RUNTIME_DATA_DIR` optionally overrides the runtime storage root used for
the embedded SQLite database. When unset, the embedded database defaults to
`<repo>/app/resources/runtime/database.db` in every environment.

## Local Profile

Source template: `settings/.env.example`

- `BACKEND_LOGS_VISIBLE=true` shows backend logs in a dedicated terminal; when absent, the launcher defaults to `true`
- intended for the local web workflow

The realtime WebSocket is deliberately restricted to loopback backend hosts and
the configured UI origin. The launcher configures a 64 KiB frame limit and
15-second native ping/10-second timeout values; the application protocol adds
its own heartbeat and sequence replay.
