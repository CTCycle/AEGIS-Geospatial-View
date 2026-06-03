# Deployment

Last updated: 2026-06-02

## Backend Persistence

- SQLite and PostgreSQL are both supported.
- Database mode is controlled by `settings/configurations.json`.
- `database.embedded_database` switches between SQLite and PostgreSQL.
- SQLite resolves to `app/resources/database.db`.

## Interoperability

- Frontend communicates with backend through `/api`.
- Development proxying is configured by `app/client/proxy.conf.cjs`.
- Desktop runtime bundles frontend dist and backend/runtime resources into the Tauri package.

## Operational Constraints

- Background jobs are in-process and do not survive backend restart.
- Cancellation is cooperative.
- Desktop packaging is Windows-focused.
- External providers influence runtime reliability based on network and credential state.

## Distribution Notes

### Web Or Local Distribution

Current scripts optimize for local execution, not a standalone server deployment bundle.

### Desktop Distribution

Build through `release/tauri/build_with_tauri.bat`.

Artifacts are exported to:

- `release/windows/installers`
- `release/windows/portable`
