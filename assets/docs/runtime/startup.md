# Startup

Last updated: 2026-08-20

## Local Development Via Launcher

```powershell
.\start_on_windows.ps1
```

The interactive launcher installs or updates portable Python, uv, and Node.js
runtimes; synchronizes backend and frontend dependencies; optionally builds the
frontend; runs tests; removes logs; clears caches; and starts backend and
frontend services. If `settings/.env` is missing, the launcher reads
`settings/.env.example` for its first-run process settings and the application
creates the local file without overwriting an existing file.

The menu provides: launch application, install/update dependencies, rebuild the
frontend independently, initialize the database explicitly, run the test suite,
remove logs, clear caches, uninstall local dependencies, and exit.

Database synchronization runs before backend repositories and background jobs
are constructed. A missing SQLite file is created, migrated, and seeded.
Existing SQLite and PostgreSQL databases are checked on every startup and
upgraded to the Alembic head when required. PostgreSQL provisioning creates the
configured database when the operator has `CREATEDB` access. Menu option 4
invokes the same idempotent workflow.

If a populated database predates Alembic, startup verifies it against the
initial baseline before stamping. Unknown or structurally different schemas
fail with an actionable error and are never silently stamped. SQLite creates a
temporary backup while a migration or first-start seed is in progress and
restores it if that operation fails.

Launch option 1 stops listeners on the configured backend/UI ports, starts the
backend, waits for `/api/health`, starts the frontend preview, waits for the UI
port, and only then opens the browser. It uses `app.server.app:app` from the
repository root when importable and falls back to `server.app:app` from
`app/server`.

When option 1 detects missing or unusable application environments, it restores
dependencies and rebuilds the frontend. A ready environment is reused without a
rebuild. Use menu option 2 to install or update dependencies and build the
frontend, or menu option 3 to rebuild the frontend without synchronizing
backend dependencies.

`BACKEND_LOGS_VISIBLE=true` (the default when absent) starts backend logs in a
separate visible terminal. Set it to `false` to start the backend detached and
hidden. After menu option 1 reports successful startup, the original launcher
terminal closes while the backend and frontend continue running.


An existing `app\server\.venv` is reused. The launcher recreates it only when
`pyvenv.cfg` references a different portable Python location, such as after the
repository or runtime folder is moved. An unrelated dependency-sync failure
does not delete the environment.

The launcher stores uv, npm, pip, Python bytecode, Ruff, pytest, Playwright,
and coverage state under `assets/cache`. Launching preserves the uv cache. Use
menu option 2 to install or update dependencies and prune it, or menu option 7
to clear all disposable development caches without reinstalling.

## Local Development Manual

Run the backend and frontend commands in separate PowerShell terminals.

```powershell
Set-Location <repository-root>
$cacheRoot = (Resolve-Path 'assets\cache').Path
$env:UV_CACHE_DIR = Join-Path $cacheRoot 'uv'
$env:PIP_CACHE_DIR = Join-Path $cacheRoot 'pip'
$env:NPM_CONFIG_CACHE = Join-Path $cacheRoot 'npm'
$env:RUFF_CACHE_DIR = Join-Path $cacheRoot 'ruff'
$env:PYTHONPYCACHEPREFIX = Join-Path $cacheRoot 'python'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $cacheRoot 'playwright-browsers'
$env:COVERAGE_FILE = Join-Path $cacheRoot 'coverage\.coverage'
$env:PYTEST_ADDOPTS = '--basetemp="' + (Join-Path $cacheRoot 'pytest-tmp') + '"'
Set-Location app/server
uv sync
uv run python -m uvicorn server.app:app --host 127.0.0.1 --port 5002 --ws-max-size 65536 --ws-ping-interval 15 --ws-ping-timeout 10
Set-Location ../client
npm install
npm run start -- --host 127.0.0.1 --port 5000
```

These ports match the values in `settings/.env.example`; if `settings/.env`
uses different `FASTAPI_PORT` or `UI_PORT` values, use those values instead.

## Alembic Development Workflow

Run these commands from `app/server` with the configured environment:

```powershell
uv run alembic current --check-heads
uv run alembic check
uv run alembic upgrade head
```

New migrations are reviewed Python modules under `app/server/migrations/versions`;
keep each revision's `down_revision` connected to the single current head and
review it before applying. The optional Alembic Mako template is intentionally
not tracked because the runtime and CI workflow do not generate revisions.
Production startup only upgrades to `head`; it never autogenerates or
downgrades schema.

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
