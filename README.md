# AEGIS Geospatial View
[![Release](https://img.shields.io/github/v/release/CTCycle/AEGIS-geographics?display_name=tag)](https://github.com/CTCycle/AEGIS-geographics/releases)
[![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)](./pyproject.toml)
[![Angular](https://img.shields.io/badge/Angular-19.2-red?logo=angular&logoColor=white)](./AEGIS/client/package.json)
[![License](https://img.shields.io/github/license/CTCycle/AEGIS-geographics)](./LICENSE)
[![CI](https://github.com/CTCycle/AEGIS-geographics/actions/workflows/ci.yml/badge.svg)](https://github.com/CTCycle/AEGIS-geographics/actions/workflows/ci.yml)

## 1. Project Overview
AEGIS Geospatial View is a chat-first geospatial assistant. Users ask for places, coordinates, and overlays in natural language, and the app returns an updated interactive map session with supporting metadata.

Key behaviors:
- Chat-first workflow for geospatial search and map updates.
- Local Ollama and API-key providers supported for model selection.
- Provider/model preferences are persisted.
- Layer metadata is sourced from JSON manifests in `AEGIS/resources/manifests`.
- Vector index bootstrap runs on first backend startup when artifacts are missing and can be rebuilt/synced manually from chat vector endpoints.
- Direct location-to-coordinates requests are supported as plain-text replies without map search execution.

## 2. Configuration Split
AEGIS uses one active runtime file: `AEGIS/settings/.env`.

Profiles:
- `AEGIS/settings/.env.local.example`
- `AEGIS/settings/.env.local.tauri.example`
- Active file: `AEGIS/settings/.env`

Runtime/process values live in `.env` and are loaded with dotenv:
- `FASTAPI_HOST`
- `FASTAPI_PORT`
- `UI_HOST`
- `UI_PORT`
- `KERAS_BACKEND`
- `MPLBACKEND`

Database settings live in `AEGIS/settings/configurations.json`:
- SQLite vs PostgreSQL switch (`database.embedded_database`)
- External PostgreSQL connection (`engine`, `host`, `port`, `database_name`, `username`, `password`, `ssl`, `ssl_ca`)
- DB tuning (`connect_timeout`, `insert_batch_size`)

## 3. Local Setup (Default)

### Windows one-click launcher

```cmd
copy /Y AEGIS\settings\.env.local.example AEGIS\settings\.env
AEGIS\start_on_windows.bat
```

The launcher prepares portable runtimes in `runtimes/`, installs dependencies, builds the frontend, and starts backend/frontend.

### macOS/Linux manual run

```bash
# from repository root
uv sync

# terminal 1
uv run python -m uvicorn AEGIS.server.app:app --host 127.0.0.1 --port 5002

# terminal 2
cd AEGIS/client
npm install
npm run start -- --host 127.0.0.1 --port 5000
```

## 4. Desktop Packaging (Windows/Tauri)

```cmd
copy /Y AEGIS\settings\.env.local.tauri.example AEGIS\settings\.env
AEGIS\start_on_windows.bat
rustup toolchain install stable-x86_64-pc-windows-msvc
rustup default stable-x86_64-pc-windows-msvc
release\tauri\build_with_tauri.bat
```

Outputs:
- `release/windows/installers`
- `release/windows/portable`

## 5. Practical Usage
1. Open the workspace.
2. Ask a geospatial question in chat (place name, coordinates, or requested overlays).
3. Review the rendered map and layer controls.
4. Open Settings to change model assignment, manage credentials, or configure Ollama.
5. Optional vector maintenance endpoints:
   - `POST /api/chat/vectors/rebuild`
   - `POST /api/chat/vectors/sync`

For full user-oriented guidance, see `assets/docs/USER_MANUAL.md`.

## 6. Testing
Run end-to-end flow:

```cmd
tests\run_tests.bat
```

Run backend unit tests:

```cmd
uv sync --extra test
uv run pytest -q tests/unit
```

Run frontend production validation:

```cmd
cd AEGIS/client
npm install
npm run build
```

## 7. Screenshots

![Geospatial search panel](figures/search_page.png)
Search and chat workspace.

![Map preview output](figures/database_browser.png)
Map canvas and output details.

## 8. Maintenance
Run `AEGIS/setup_and_maintenance.bat` for routine maintenance tasks (cleanup, DB initialization, layer updates, and build artifact cleanup).

## 9. License
This project is licensed under the MIT license. See `LICENSE`.
