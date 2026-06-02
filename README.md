# AEGIS Geospatial View
[![Release](https://img.shields.io/github/v/release/CTCycle/AEGIS-geographics?display_name=tag)](https://github.com/CTCycle/AEGIS-geographics/releases)
[![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?logo=python&logoColor=white)](./app/server/pyproject.toml)
[![Angular](https://img.shields.io/badge/Angular-19.2-red?logo=angular&logoColor=white)](./app/client/package.json)
[![License](https://img.shields.io/github/license/CTCycle/AEGIS-geographics)](./LICENSE)
[![CI](https://github.com/CTCycle/AEGIS-geographics/actions/workflows/ci.yml/badge.svg)](https://github.com/CTCycle/AEGIS-geographics/actions/workflows/ci.yml)

## Structure
- `app/server`: FastAPI backend (Python root for `uv sync`).
- `app/client`: Angular frontend + Tauri host.
- `app/resources`: data, vectors, DB, logs.
- `app/tests`: unit/e2e suites.
- `app/scripts`: backend helper scripts.
- `app/shared`: shared API artifacts (for example generated `openapi.json`).
- `settings`: runtime `.env` and `configurations.json`.
- `runtimes`: portable Node/Python/uv runtimes only.

## Local Setup (Windows)
```cmd
copy /Y settings\.env.local.example settings\.env
start_on_windows.bat
```

## Local Setup (macOS/Linux)
```bash
cd app/server
uv sync

# terminal 1
uv run python -m uvicorn server.app:app --host 127.0.0.1 --port 5002

# terminal 2
cd ../client
npm install
npm run start -- --host 127.0.0.1 --port 5000
```

## Desktop Packaging (Windows/Tauri)
```cmd
copy /Y settings\.env.local.tauri.example settings\.env
start_on_windows.bat
rustup toolchain install stable-x86_64-pc-windows-msvc
rustup default stable-x86_64-pc-windows-msvc
release\tauri\build_with_tauri.bat
```

## Testing
```cmd
app\tests\run_tests.bat
```

```bash
cd app/server
uv sync --extra test
uv run pytest -q ../tests/unit
```

## Maintenance
Run `setup_and_maintenance.bat`.

## License
This project is licensed under the **MIT License**. See `LICENSE` for full terms.
