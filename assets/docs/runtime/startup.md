# Startup

Last updated: 2026-06-03

## Local Development Via Launcher

```cmd
copy /Y settings\.env.local.example settings\.env
start_on_windows.bat
```

The launcher installs or updates portable runtimes, syncs backend dependencies, installs frontend dependencies, builds when needed, and starts backend and frontend services.

## Local Development Manual

```powershell
uv sync
uv run python -m uvicorn server.app:app --host 127.0.0.1 --port 7059
Set-Location app/client
npm install
npm run start -- --host 127.0.0.1 --port 4512
```

## Desktop Packaging

```cmd
copy /Y settings\.env.local.tauri.example settings\.env
start_on_windows.bat
release\tauri\build_with_tauri.bat
```

## Test Execution

```cmd
app\tests\run_tests.bat
```
