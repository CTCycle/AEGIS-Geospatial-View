# Deployment

Last updated: 2026-07-11

## Backend Persistence

- SQLite and PostgreSQL are both supported.
- Database mode is controlled by `settings/.env` or runtime environment variables.
- `EMBEDDED_DATABASE` switches between SQLite and PostgreSQL.
- SQLite resolves to `app/resources/database.db`.

## Interoperability

- Frontend communicates with backend through `/api`.
- Development proxying is configured by `app/client/proxy.conf.cjs`.
- The Windows launcher runs the backend and frontend preview as local processes.

## Operational Constraints

- Background jobs are in-process and do not survive backend restart.
- Cancellation is cooperative.
- External providers influence runtime reliability based on network and credential state.

## Distribution Notes

Current scripts optimize for local execution, not a standalone server distribution bundle. Use `start_on_windows.ps1` for the supported Windows workflow or the manual commands in `runtime/startup.md`.
