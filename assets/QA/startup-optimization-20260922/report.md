# Windows startup optimization validation

Date: 2026-09-22  
Branch: `loop-dev`  
Revision under test: `9c2da7a47167a507899759a1cab79008239c2a28` (working tree changes are not committed)

## Scope

Implemented the Windows launch port-consent guard, dependency/build state checks, process-aware health waits and cleanup, concurrent backend/frontend launch, provider-I/O-free persisted-settings validation, shared geospatial catalog snapshot, and mutation-aware SQLite backup behavior. Angular continues to launch through the existing `ng serve` path, as specified by the implementation plan.

Startup runs used an isolated `AEGIS_DATA_DIR` under this QA directory. The configured `settings/.env` file was restored byte-for-byte after each run. The user's persistent database was not used. Temporary database and log files were removed after recording this report.

## Launcher and browser evidence

- Current dependencies and production build: one warm launch completed in **19,285 ms**. Launcher output confirmed dependency installation and production rebuild were both skipped; backend health and frontend readiness passed. Backend and frontend launch commands were issued before either readiness wait.
- The in-app Browser rendered `http://127.0.0.1:4512/`, titled **AEGIS | Search workspace**, with the Search workspace ready state and map workspace visible. The isolated runtime had no configured model, and the model control showed **Needs attention**. No provider readiness claim is made.
- Production source edit: **16,538 ms**, one production build, final build state `Current`.
- Test-only source edit: **9,072 ms**, no production build, final build state `Current`.
- Missing build marker: **18,173 ms**, one production build, final build state `Current`.
- Missing frontend dependency marker: launcher repaired the environment with `uv sync` and `npm ci`, reused the current production build, and reached backend and frontend readiness. The Development Python extras were restored afterward.
- Explicit install/update, explicit rebuild, and menu exit paths completed. `app/client/package-lock.json` is unchanged.
- The at-head isolated SQLite startup completed without creating a backup. Migration checks on an isolated database passed: `alembic upgrade head`, `alembic check` (`No new upgrade operations detected`), and `alembic current --check-heads` (`202609210001 (head)`).

## Port-conflict guard evidence

- Non-interactive launch with an occupied UI port failed non-zero and left the controlled listener alive.
- Interactive decline returned to the menu without stopping the listener.
- Interactive consent for one occupied port terminated the confirmed listener and allowed startup.
- Two different PIDs on the backend and UI ports were both listed; non-interactive launch failed and preserved both listeners.
- One controlled Python PID owning both ports was shown once with both ports, confirmed once, and terminated once. Startup then succeeded.
- Launcher-created backend/frontend processes were stopped after validation; ports `7059`, `4512`, and `9876` were clear at report time.

Protected-process and ownership-change races were not simulated. A forced backend/frontend readiness failure was not injected, so failed-start cleanup is supported by code and unit/contract checks but lacks a live fault-injection run.

## Automated checks

- Frontend state helper: **19 passed**.
- Angular unit suite: **248 passed**.
- Focused CI backend suites, including startup, persistence, and canonical runtime contract coverage: **401 passed, 1 deselected**. The deselected test enumerates pre-existing pytest cache paths that are inaccessible under this Windows account; the same protected paths caused the earlier local failure.
- Ruff: **passed**.
- Strict Pyright: **1 error** in unchanged `app/server/services/agent/tool_handlers/location.py:118:44` (`"group" is not a known attribute of "None"`, `reportOptionalMemberAccess`). No unrelated typing change was made.
- PowerShell parser, `git diff --check`, isolated migration checks, frontend production builds, and dependency/build marker states passed.

## Measurement and coverage limits

No same-machine pre-change warm-launch measurement was captured, so the **19,285 ms** observation is a post-change sample and does not establish a speedup. It is one run, not a statistical benchmark. The plan's dynamic-provider-outage health check and live failed-service cleanup scenario remain unverified. Browser appearance was inspected live, but no screenshot was retained. The existing Angular dev server still performs its normal startup compilation.
