# Startup

Last updated: 2026-06-04

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

## Codex And Sandbox Note

On Windows inside the Codex workspace sandbox, Angular 19 frontend commands that depend on `esbuild` may fail with `spawn EPERM` even when `node`, `npm`, and `esbuild.exe` are present and executable.

Observed behavior:

- Direct shell execution of `esbuild.exe` succeeds.
- `node:child_process.spawn(...)` fails with `EPERM` for `esbuild.exe`, `cmd.exe`, and even another `node.exe` when the Node parent process is sandboxed.
- As a result, `npm run build`, `npm run start`, and `npm run preview` can fail inside the sandbox because Angular uses `esbuild` through a spawned child process.

Working path:

- Run frontend Angular commands outside the sandbox when using Codex on Windows.
- The same project build succeeds once the command is executed with elevated or unsandboxed permissions.
- Backend FastAPI startup is not affected by this specific issue.

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
