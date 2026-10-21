# Deployment

Last updated: 2026-10-21

## Backend persistence

AEGIS is a local SQLite application. The database file defaults to
`<repo>/data/runtime/database.db` and can be moved by setting
`AEGIS_DATA_DIR` to a directory that the application can read and write.

An empty database file is initialized at the current Alembic head,
`202608200001`, and seeded on first startup. Existing files must use that same
revision; unknown and retired revisions are rejected and require an explicit
rebuild or separately reviewed migration. A populated file without an Alembic
revision is rejected; startup never stamps, deletes, or silently replaces
existing data. The migration workflow takes a temporary backup and restores it
if migration or first-start seeding fails.

Back up the SQLite file before upgrading the application. If a legacy or
corrupt file cannot be opened, preserve it for investigation and create a new
data directory only after the original has been safely copied.

## Interoperability

- the frontend communicates with the backend through `/api`;
- development proxying is configured by `app/client/proxy.conf.cjs`;
- the Windows launcher runs the backend and frontend as local processes using
  the portable runtimes under `runtimes/`.

## Operational constraints

- SQLite permits one writer at a time; AEGIS uses WAL, a busy timeout, short
  transactions, and per-operation sessions for normal local concurrency;
- active run execution occurs in the backend process; run state and event
  history are persisted in SQLite;
- cancellation is cooperative;
- external data sources influence runtime reliability based on network and
  credential state;
- a load-balanced deployment is outside the supported single-process runtime
  model.

## Distribution notes

Current scripts optimize for local execution rather than a standalone server
bundle. Use `start_on_windows.ps1` for the supported Windows workflow or the
manual commands in `assets/docs/runtime/startup.md`. There is no first-class
container or hosted deployment manifest in this checkout.
