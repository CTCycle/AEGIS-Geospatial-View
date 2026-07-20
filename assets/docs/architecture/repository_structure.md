# Repository Structure

Last updated: 2026-07-20

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
    .env.example
    configurations.json
  scripts/
    launcher/
  start_on_windows.ps1
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
  Persistence, serialization, database helpers, credential encryption material, and reference catalog seeding.
- `services/`
  Runtime orchestration for agent, chat, geospatial, LLM, and search workflows.
  The agent orchestration area now includes focused helpers such as `turn_history.py`, `turn_state_assembler.py`, and `turn_support.py` to keep `AgentOrchestrator` under the repository Python size constraint without changing the public chat-turn contract.

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
- `cameras/*.json`
- `transit/*.json`
- `reference/*.json`

## Tests

- E2E tests: `app/tests/e2e/*.py`
- Unit tests: `app/tests/unit/**/*.py`
- Test runner: `app/tests/run_tests.bat`
