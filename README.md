# AEGIS Geospatial View

## 1. Project Overview
AEGIS Geospatial View turns place names or coordinates into consistent bounding boxes and previewable map imagery. The system includes a FastAPI backend for geocoding, imagery selection, and metadata preparation, plus a React frontend for interactive search and preview.

## 2. Runtime Model (Local Default + Docker Cloud)
AEGIS uses one active runtime file: `AEGIS/settings/.env`.

- Local mode is the default workflow and runs without Docker.
- Cloud mode runs with Docker (`backend` + `frontend`).
- Desktop packaging runs with Tauri and a local packaged backend.
- Mode switching is configuration-only: copy one profile into `AEGIS/settings/.env`.

Runtime profiles:
- `AEGIS/settings/.env.local.example`
- `AEGIS/settings/.env.local.tauri.example`
- `AEGIS/settings/.env.cloud.example`
- Active file: `AEGIS/settings/.env`

## 3. Local Mode (Default)

### 3.1 Windows One-Click Launcher
Run:

```cmd
AEGIS\start_on_windows.bat
```

The launcher:
1. Downloads portable Python/uv/Node runtimes into `runtimes/` (repository root)
2. Installs backend dependencies into `runtimes/.venv`
3. Writes the runtime lockfile to `runtimes/uv.lock`
4. Installs frontend dependencies (uses `npm ci` when lockfile exists, fallback to `npm install`)
5. Builds frontend
6. Starts backend + frontend

Before running, set the active profile as local defaults:

```cmd
copy /Y AEGIS\settings\.env.local.example AEGIS\settings\.env
```

### 3.2 macOS/Linux Manual Local Run

```bash
# from repository root
uv sync

# terminal 1
uv run python -m uvicorn AEGIS.server.app:app --host 127.0.0.1 --port 5002

# terminal 2
cd AEGIS/client
npm install
npm run dev -- --host 127.0.0.1 --port 5000
```

### 3.3 Windows Desktop Packaging (Tauri)
Prepare the desktop runtime profile:

```cmd
copy /Y AEGIS\settings\.env.local.tauri.example AEGIS\settings\.env
```

Ensure the portable runtimes exist:

```cmd
AEGIS\start_on_windows.bat
```

Ensure Rust (MSVC toolchain) is installed for Tauri:

```cmd
rustup toolchain install stable-x86_64-pc-windows-msvc
rustup default stable-x86_64-pc-windows-msvc
```

Build the packaged desktop artifacts:

```cmd
release\tauri\build_with_tauri.bat
```

The user-facing outputs are exported to:

- `release/windows/installers`
- `release/windows/portable`

Regenerate desktop icon assets from the shared favicon source:

```cmd
cd AEGIS\client
npm run tauri:icon
```

Clean desktop build outputs:

```cmd
cd AEGIS\client
npm run tauri:clean
```

## 4. Cloud Mode (Docker)

1. Activate cloud profile:

```cmd
copy /Y AEGIS\settings\.env.cloud.example AEGIS\settings\.env
```

2. Build images:

```bash
docker compose --env-file AEGIS/settings/.env build --no-cache
```

3. Start containers:

```bash
docker compose --env-file AEGIS/settings/.env up -d
```

4. Stop containers:

```bash
docker compose --env-file AEGIS/settings/.env down
```

Cloud topology:
- `backend`: FastAPI/Uvicorn (`:8000` internal)
- `frontend`: Nginx serving SPA
- Same-origin `/api/*` proxy from frontend to `http://backend:8000/`

## 5. Configuration Contract
Runtime keys in `AEGIS/settings/.env`:

- `FASTAPI_HOST`, `FASTAPI_PORT`, `UI_HOST`, `UI_PORT`, `VITE_API_BASE_URL`, `RELOAD`
- `DB_EMBEDDED`, `DB_ENGINE`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- `DB_SSL`, `DB_SSL_CA`, `DB_CONNECT_TIMEOUT`, `DB_INSERT_BATCH_SIZE`
- `OPTIONAL_DEPENDENCIES`, `MPLBACKEND`, `KERAS_BACKEND`

`AEGIS/settings/configurations.json` remains the non-runtime fallback source.

## 6. Tests
Run automated E2E flow:

```cmd
tests\run_tests.bat
```

The runner resolves host/port from `AEGIS/settings/.env`, exports:
- `APP_TEST_FRONTEND_URL`
- `APP_TEST_BACKEND_URL`

and uses those URLs for readiness checks and pytest runtime config.

## 7. Screenshots

![Geospatial search panel](figures/search_page.png)
Search toolbar for entering a place or coordinates and selecting imagery options.

![Map preview output](figures/database_browser.png)
Map canvas area showing the generated output and summary metadata.

## 8. Setup and Maintenance
Run `AEGIS/setup_and_maintenance.bat` for routine tasks:

- Remove logs
- Uninstall app runtime artifacts
- Initialize database
- Update NASA GIBS layers
- Clean desktop build artifacts

## 9. License
This project is licensed under the MIT license. See `LICENSE`.
