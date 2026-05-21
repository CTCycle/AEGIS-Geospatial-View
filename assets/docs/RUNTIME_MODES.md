# Runtime Modes

Last updated: 2026-05-21

## Supported Modes

### 1. Local development (web app + API)

- Backend: FastAPI (`AEGIS.server.app:app`)
- Frontend: Angular dev/preview server (`app/client`)
- Primary launcher: `AEGIS/start_on_windows.bat`
- Portable runtimes are expected under `runtimes/` (Python, uv, Node.js)

### 2. Desktop runtime and packaging (Tauri on Windows)

- Tauri config: `app/client/src-tauri/tauri.conf.json`
- Build pipeline: `release/tauri/build_with_tauri.bat`
- Output artifacts:
  - `release/windows/installers`
  - `release/windows/portable`

### 3. Automated test runtime

- Test orchestrator: `tests/run_tests.bat`
- Starts backend + frontend and runs pytest (including Playwright-based E2E)

### 4. Browser validation tooling

- The Codex Browser Use Node REPL runtime requires Node.js `>=22.22.0`.
- If the active `node` resolves below that version (for example `v20.19.5`), Browser Use will fail before opening the in-app browser.
- In that case, use the available Playwright MCP browser tools for local UI validation, or point `NODE_REPL_NODE_PATH` at a compatible Node.js runtime before retrying Browser Use.

### Not currently implemented

- No first-class Docker/container deployment files are present.
- No Linux/macOS desktop packaging pipeline is defined in repo scripts.

## Startup Procedures

### Local development via launcher (Windows CMD)

```cmd
copy /Y AEGIS\settings\.env.local.example AEGIS\settings\.env
AEGIS\start_on_windows.bat
```

What it does:
- installs/updates portable Python, uv, Node
- syncs Python dependencies via `uv`
- installs frontend dependencies
- builds frontend if needed
- starts backend and frontend with configured host/port

### Local development manual (PowerShell)

```powershell
uv sync
uv run python -m uvicorn AEGIS.server.app:app --host 127.0.0.1 --port 7059
Set-Location app/client
npm install
npm run start -- --host 127.0.0.1 --port 4512
```

### Desktop packaging (Windows CMD)

```cmd
copy /Y AEGIS\settings\.env.local.tauri.example AEGIS\settings\.env
AEGIS\start_on_windows.bat
release\tauri\build_with_tauri.bat
```

### Test execution (Windows CMD)

```cmd
tests\run_tests.bat
```

## Environment Variables and Configuration

### `.env` (`AEGIS/settings/.env`)

Common runtime keys:
- `FASTAPI_HOST`
- `FASTAPI_PORT`
- `UI_HOST`
- `UI_PORT`
- `RELOAD`
- `OPTIONAL_DEPENDENCIES`

### `configurations.json` (`AEGIS/settings/configurations.json`)

Defines:
- database mode and connection settings
- job polling interval
- geospatial bounds and service settings
- chat/vector defaults and thresholds
- provider-specific request tuning

## Configuration Differences

### Development profile (`.env.local.example`)

- `OPTIONAL_DEPENDENCIES=true`
- intended for local web workflow with optional extras available

### Tauri profile (`.env.local.tauri.example`)

- `OPTIONAL_DEPENDENCIES=false`
- intended for deterministic desktop packaging workflow

### Database mode switch

- `database.embedded_database=true` -> SQLite (`app/resources/database.db`)
- `database.embedded_database=false` -> PostgreSQL backend using JSON credentials/settings

## Interoperability

- Frontend talks to backend through `/api` routes.
- In development, proxying is configured by `app/client/proxy.conf.cjs`.
- Chat and map features share backend services and persistence layers.
- Desktop runtime bundles frontend dist + backend/runtime resources into Tauri package resources.

## Limitations and Constraints

- Background jobs are in-process and memory-backed; they do not survive backend restart.
- Job cancellation is cooperative, not force-kill.
- Desktop packaging flow is Windows-focused in current scripts.
- External geospatial/LLM providers affect runtime behavior and reliability based on connectivity and credentials.

## Deployment Notes

### Web/local distribution

- Current repository scripts optimize for local execution rather than a standalone server deployment package.

### Desktop distribution

- Build from `release/tauri/build_with_tauri.bat`.
- Exported artifacts are copied to:
  - `release/windows/installers` (`.msi`, setup executable)
  - `release/windows/portable` (portable executable bundle)
- Tauri bundle includes staged runtime resources (Python/uv/settings/server scripts) per `tauri.conf.json` and build helper script.
