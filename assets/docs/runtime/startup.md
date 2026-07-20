# Startup

Last updated: 2026-07-20

## Local Development Via Launcher

```powershell
.\start_on_windows.ps1
```

The interactive launcher installs or updates portable Python, uv, and Node.js
runtimes; synchronizes backend and frontend dependencies; optionally builds the
frontend; initializes or reseeds the database; runs tests; removes logs; clears
caches; and starts backend and frontend services. On first launch it copies
`settings/.env.example` to `settings/.env`.

The menu provides: launch application, install/update dependencies, initialize
the database, run the test suite, remove logs, clear caches, uninstall local
dependencies, and exit.

Set `ALWAYS_REBUILD=false` in `settings/.env` to skip the frontend build during
application startup. The default is `true`.

`BACKEND_LOGS_VISIBLE=true` (the default when absent) starts backend logs in a
separate visible terminal. Set it to `false` to start the backend detached and
hidden. After menu option 1 reports successful startup, the original launcher
terminal closes while the backend and frontend continue running.


An existing `app\server\.venv` is reused. The launcher recreates it only when
`pyvenv.cfg` references a different portable Python location, such as after the
repository or runtime folder is moved. An unrelated dependency-sync failure
does not delete the environment.

Launching preserves the uv cache. Use menu option 2 to install or update dependencies and prune it, or menu option 6 to clear caches without reinstalling.

## Local Development Manual

```powershell
uv sync
Set-Location app
uv run python -m uvicorn server.app:app --host 127.0.0.1 --port 7059
Set-Location app/client
npm install
npm run start -- --host 127.0.0.1 --port 4512
```

## Codex And Sandbox Note

On Windows inside the Codex workspace sandbox, Angular 22 frontend commands that depend on `esbuild` may fail with `spawn EPERM` even when `node`, `npm`, and `esbuild.exe` are present and executable.

Observed behavior:

- Direct shell execution of `esbuild.exe` succeeds.
- `node:child_process.spawn(...)` fails with `EPERM` for `esbuild.exe`, `cmd.exe`, and even another `node.exe` when the Node parent process is sandboxed.
- As a result, `npm run build`, `npm run start`, and `npm run preview` can fail inside the sandbox because Angular uses `esbuild` through a spawned child process.

Working path:

- Run frontend Angular commands outside the sandbox when using Codex on Windows.
- The same project build succeeds once the command is executed with elevated or unsandboxed permissions.
- Backend FastAPI startup is not affected by this specific issue.

## Test Execution

```cmd
app\tests\run_tests.bat
```

For bounded backend-only validation without starting local servers or Angular:

```cmd
set STANDARD_TEST_SKIP_LIVE_SERVERS=true
set STANDARD_TEST_SKIP_FRONTEND=true
set STANDARD_TEST_PYTEST_TARGET=app\tests\unit
app\tests\run_tests.bat
```
