# Configuration

Last updated: 2026-06-03

## Environment File

Primary runtime environment file: `settings/.env`

Common keys include:

- `FASTAPI_HOST`
- `FASTAPI_PORT`
- `UI_HOST`
- `UI_PORT`
- `RELOAD`
- `OPTIONAL_DEPENDENCIES`

## Structured Configuration

`settings/configurations.json` defines:

- database mode and connection settings
- job polling interval
- geospatial bounds and service tuning
- chat defaults
- provider-specific request tuning

## Profile Differences

### Development Profile

Source template: `settings/.env.local.example`

- `OPTIONAL_DEPENDENCIES=true`
- intended for local web workflow

### Tauri Profile

Source template: `settings/.env.local.tauri.example`

- `OPTIONAL_DEPENDENCIES=false`
- intended for deterministic desktop packaging
