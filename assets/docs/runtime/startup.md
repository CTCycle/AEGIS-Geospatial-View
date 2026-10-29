# Startup

Last updated: 2026-10-29

## Local Development Via Launcher

```powershell
.\start_on_windows.ps1
```

Use `-WhatIf` to preview the exact paths for any cleanup action:

```powershell
.\start_on_windows.ps1 -Action ClearCache -WhatIf
.\start_on_windows.ps1 -Action Uninstall -WhatIf
.\start_on_windows.ps1 -Action RemoveAllData -WhatIf
```

`-Action ClearCache` strictly clears `runtimes/cache`, recognized source-local
cache leftovers, the generated client build, and the Mobility Database catalog
cache. Locked or inaccessible paths are reported and cause a non-zero exit.
Direct cleanup actions require an interactive confirmation or `-ConfirmRemoval`
after reviewing their `-WhatIf` preview; menu actions continue to ask for
confirmation.

The interactive launcher installs or updates portable Python 3.14.7, uv, and
Node.js runtimes; synchronizes backend and frontend dependencies; optionally
builds the frontend; runs tests; removes logs; clears caches; and starts
backend and frontend services. If `settings/.env` is missing, the launcher reads
`settings/.env.example` for its first-run process settings and the application
creates the local file without overwriting an existing file.

An explicit non-empty `AEGIS_DATA_DIR` inherited from the parent process takes
precedence over the value in `settings/.env` for the launched backend. When no
process override is supplied, the launcher uses the environment-file value; a
blank value keeps the default `data/runtime` root.

The menu is grouped into clear sections. Application options launch the
application, install or update dependencies, rebuild the frontend independently,
and initialize the database explicitly. Maintenance options run the test suite,
remove logs, clear caches, and uninstall local dependencies. Cleanup previews
enumerate the exact paths, then remove them in a deterministic, deepest-first
order. Locked, inaccessible, and reparse-point paths are reported; cleanup does
not follow symbolic links or junctions. Uninstallation removes managed runtimes,
dependencies, generated builds, caches, and application logs while preserving
settings, databases, ingested data, vectors, source catalogs, and retained QA
evidence. The separate remove-all-data action lists and confirms the active
SQLite file and companions, recognized geospatial/vector data, and logs; unknown
files beside a custom data root are preserved. The update action
requires a non-detached, clean checkout of `main` and pulls it with
`git pull --ff-only origin main`; it never switches branches or modifies local
changes. The check action reports `origin/main` status without downloading or
applying changes. Data management can remove the SQLite database,
runtime/provider data, ingested files, generated vectors, and logs while
preserving application source files. The final option exits the launcher.

Startup loads and validates `<AEGIS_DATA_DIR or data/runtime>/database-settings.json`
before opening a database, so selecting the database never depends on database
contents. A first-run file defaults to `database.db`; database synchronization
runs before repositories and run-lifecycle services are constructed. A missing
SQLite file is initialized at the current revision, `202608200001`, and seeded.
Existing files must already use that revision; unknown and retired revisions
fail with an actionable error and are never stamped or replaced. Menu option 4
invokes the same guarded workflow. A populated database without an Alembic
revision and structurally invalid files are also rejected. The migration lock
protects read-only schema and required-seed checks. SQLite creates a temporary
backup before an existing database is mutated and restores it if migration or
seeding fails.

New databases seed the typed `application_runtime_settings` row with built-in
defaults. Existing rows remain authoritative, and startup does not read runtime
settings from JSON files.

The Settings Database section can test and switch the active SQLite file while
the server is running. A switch validates and prepares the target first, then
is rejected if requests or WebSockets or active agent runs are in flight. A
failed activation rolls back to the prior database and config.
The browser reloads its client state after success so the selected database's
settings are visible immediately. A switch never copies records between
databases. Changing `AEGIS_DATA_DIR` or process-level hosts, ports, and reload
configuration still requires an application restart.

Launch option 1 checks the configured backend port (`FASTAPI_PORT`) before
dependency work and again before starting the service. If the port is occupied,
it shows the grouped PID, process name, and occupied ports, then accepts only an
explicit `y` or `yes` before terminating each confirmed process tree once.
Declining cancels the launch; non-interactive launch fails without terminating
existing processes. It starts only the backend, which serves the built frontend
and the API from one origin, waits for `/api/health` and for `/` to return the
SPA index, opens `http://<FASTAPI_HOST>:<FASTAPI_PORT>/`, and then stays in the
foreground as the lifecycle owner. If readiness fails, only the process tree
created by that launch is cleaned up. It launches the venv Python directly
with `server.app:app` from the `app` directory and does not support an
alternate import root, stale launcher arguments, or compatibility fallback.
The launcher reports elapsed milliseconds for major launch steps and the total
time to application readiness. Timings include any time spent answering port
conflict prompts.
The native route rejects provider aliases and never substitutes a different
provider or model after a configured provider failure.

Press Ctrl+C in the launcher to stop. The backend shares the launcher console,
receives the interrupt, and runs its normal shutdown; the launcher waits up to
10 seconds and then terminates only the process tree it started. A backend that
exits on its own is reported with its exit code. `UI_HOST` and `UI_PORT` apply
only to the Angular dev server.

Option 1 validates Python runtime dependencies and a content fingerprint for
frontend dependencies. It synchronizes dependencies only when that state is
missing or stale, then checks a separate production-build fingerprint. The
build marker records sorted SHA-256 input and output hashes plus the Node
version; a missing or stale build is rebuilt, while a current build is reused.
The build fingerprint excludes test-only source, E2E fixtures, proxy settings,
Karma configuration, and backend or documentation changes. Dependency and
build state markers live under the already ignored `node_modules` and `dist`
directories. Use menu option 2 to install or update dependencies and build the
frontend, or menu option 3 to rebuild the frontend without synchronizing
backend dependencies.

`BACKEND_LOGS_VISIBLE=true` (the default when absent) shows backend logs in the
launcher console. Set it to `false` to write backend output to
`data/logs/backend-console.log` and `backend-console.err.log` instead; Ctrl+C
still stops the backend gracefully. The launcher requires PowerShell 7+ (`pwsh`)
and refuses to run under Windows PowerShell 5.1.

An existing `app\server\.venv` is reused. The launcher recreates it only when
`pyvenv.cfg` references a different portable Python location, such as after the
repository or runtime folder is moved. An unrelated dependency-sync failure
does not delete the environment.

The launcher and test runner store disposable runtime and test caches under
`runtimes/cache`, including uv, npm, pip, Python bytecode, Playwright, Ruff,
pytest, Angular, coverage, test-runtime databases, and the Mobility Database
catalog. Cache cleanup also removes recognized legacy cache folders at the
repository root and under backend, tests, validation scripts, and client, the
old `app/runtimes/cache` test-runtime location, and the generated client `dist`
output. It leaves application logs, databases, ingested datasets, vectors, and
retained QA evidence intact; only the exact Mobility Database catalog cache
file is removed from its legacy geospatial-data location. Persistent data under
`data/runtime`, `data/geospatial`, and `data/vectors` is removed only by the
separate remove-all-data action after its paths are displayed and confirmed.
Application logs under `data/logs` are removed by the remove-logs, uninstall,
or remove-all-data action.

## Local Development Manual

Production-style run: build the frontend (`npm run build` in `app/client`) and run
the backend command below; it serves the UI at the backend port. For frontend
development, also run the Angular dev server in a second PowerShell terminal.

```powershell
Set-Location <repository-root>
$runtimeCacheRoot = (Resolve-Path 'runtimes\cache').Path
$env:AEGIS_CACHE_ROOT = $runtimeCacheRoot
$env:UV_CACHE_DIR = Join-Path $runtimeCacheRoot 'uv'
$env:PIP_CACHE_DIR = Join-Path $runtimeCacheRoot 'pip'
$env:NPM_CONFIG_CACHE = Join-Path $runtimeCacheRoot 'npm'
$env:PYTHONPYCACHEPREFIX = Join-Path $runtimeCacheRoot 'python'
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $runtimeCacheRoot 'playwright-browsers'
$env:RUFF_CACHE_DIR = Join-Path $runtimeCacheRoot 'ruff'
$env:COVERAGE_FILE = Join-Path $runtimeCacheRoot 'coverage\.coverage'
$env:PYTEST_ADDOPTS = '--basetemp="' + (Join-Path $runtimeCacheRoot 'pytest-tmp') + '"'
Set-Location app/server
uv sync
uv run python -m uvicorn server.app:app --host 127.0.0.1 --port 5002 --ws-max-size 65536 --ws-ping-interval 15 --ws-ping-timeout 10
# Development only: Angular dev server with /api proxy
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

The cache-cleanup menu option can be run before this command from a clean
machine state. It clears the canonical cache tree and recognized local cache
residue, recreates `runtimes/cache`, and leaves persistent application data and
retained QA evidence untouched.

For bounded backend-only validation without starting local servers or Angular:

```cmd
set STANDARD_TEST_SKIP_LIVE_SERVERS=true
set STANDARD_TEST_SKIP_FRONTEND=true
set STANDARD_TEST_PYTEST_TARGET=app\tests\unit
app\tests\run_tests.bat
```
