# AEGIS Geospatial View

## 1. Project Overview
AEGIS Geospatial View is a chat-first geospatial assistant. Users ask for places, coordinates, and overlays in natural language, and the app returns an updated interactive map session with supporting metadata.

Key behaviors:
- Chat-first workflow for geospatial search and map updates.
- Local Ollama and cloud providers supported for model selection.
- Provider/model preferences are persisted.
- Layer metadata is sourced from JSON manifests in `AEGIS/resources/manifests`.
- Vector index is created on first use and can be rebuilt from Settings.

## 2. Runtime Modes
AEGIS uses one active runtime file: `AEGIS/settings/.env`.

Profiles:
- `AEGIS/settings/.env.local.example`
- `AEGIS/settings/.env.local.tauri.example`
- `AEGIS/settings/.env.cloud.example`
- Active file: `AEGIS/settings/.env`

Use local mode for development, cloud mode for Docker deployment, and Tauri profile for desktop packaging.

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
npm run dev -- --host 127.0.0.1 --port 5000
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

## 5. Cloud Mode (Docker)

```cmd
copy /Y AEGIS\settings\.env.cloud.example AEGIS\settings\.env
docker compose --env-file AEGIS/settings/.env build --no-cache
docker compose --env-file AEGIS/settings/.env up -d
```

Stop:

```cmd
docker compose --env-file AEGIS/settings/.env down
```

## 6. Practical Usage
1. Open the workspace.
2. Ask a geospatial question in chat (place name, coordinates, or requested overlays).
3. Review the rendered map and layer controls.
4. Open Settings to change model assignment, manage credentials, or configure Ollama.

For full user-oriented guidance, see `assets/docs/USER_MANUAL.md`.

## 7. Testing
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

## 8. Screenshots

![Geospatial search panel](figures/search_page.png)
Search and chat workspace.

![Map preview output](figures/database_browser.png)
Map canvas and output details.

## 9. Maintenance
Run `AEGIS/setup_and_maintenance.bat` for routine maintenance tasks (cleanup, DB initialization, layer updates, and build artifact cleanup).

## 10. License
This project is licensed under the MIT license. See `LICENSE`.
