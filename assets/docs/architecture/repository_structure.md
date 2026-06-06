# Repository Structure

Last updated: 2026-06-03

## Purpose

This file inventories the source and operational layout of the repository. Generated directories such as `node_modules`, `dist`, `.angular`, and `__pycache__` are intentionally excluded.

## Repository Root

```text
AEGIS Geospatial View/
  app/
    client/
      src/
      package.json
      proxy.conf.cjs
    resources/
      catalog/
      database.db
    src-tauri/
      gen/
      icons/
      src/
      target/
    scripts/
    server/
      api/
      common/
      configurations/
      domain/
      repositories/
      services/
      app.py
    shared/
    tests/
      e2e/
      unit/
      run_tests.bat
  settings/
    .env
    .env.local.example
    .env.local.tauri.example
    configurations.json
  start_on_windows.bat
  setup_and_maintenance.bat
  release/
    tauri/
  README.md
```

## Backend Areas

Key backend directories under `app/server`:

- `api/`
  FastAPI routes for chat, geospatial, and search.
- `common/`
  Shared constants, logging, time, and common types.
- `configurations/`
  Environment loading, settings composition, and startup config.
- `domain/`
  Request/response contracts and domain models.
- `repositories/`
  Persistence, serialization, database helpers, and reference catalog loading/seeding.
- `services/`
  Runtime orchestration for agent, chat, geospatial, LLM, and search workflows.

## Frontend Areas

Key frontend directories under `app/client/src/app`:

- `components/`
  Reusable UI building blocks.
- `core/`
  API client, state contracts, constants, and shared services.
- `pages/`
  Route-level page components.

## Catalog Areas

`app/resources/catalog` contains manifest-backed geospatial configuration:

- `index.json`
- `runtime_profiles.json`
- `providers/*.json`
- `basemaps/*.json`
- `overlays/*.json`
- `tools/*.json`
- `reference/*.json`

## Tests

- E2E tests: `app/tests/e2e/*.py`
- Unit tests: `app/tests/unit/**/*.py`
- Test runner: `app/tests/run_tests.bat`
