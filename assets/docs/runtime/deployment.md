# Deployment

Last updated: 2026-08-20

## Backend Persistence

- SQLite and PostgreSQL are both supported.
- Database mode is controlled by `settings/.env` or runtime environment variables.
- `EMBEDDED_DATABASE` switches between SQLite and PostgreSQL.
- Embedded SQLite resolves to `<repo>/app/resources/runtime/database.db` by
  default in every environment.
- Set `AEGIS_RUNTIME_DATA_DIR` to override the embedded database directory.
- Missing SQLite files are created, migrated to the Alembic head, and seeded on
  first application startup.
- Every startup checks SQLite and PostgreSQL against the Alembic head and
  applies pending migrations before serving requests.
- PostgreSQL provisioning creates the configured database when permitted; the
  explicit `start_on_windows.ps1` initialization option uses the same workflow.
- Startup never autogenerates or downgrades migrations. A failed migration
  prevents readiness; SQLite restores its pre-migration backup.

## Interoperability

- Frontend communicates with backend through `/api`.
- Development proxying is configured by `app/client/proxy.conf.cjs`.
- The Windows launcher runs the backend and frontend preview as local processes
  using the portable runtimes under `runtimes/`.

## Operational Constraints

- Background jobs are in-process and do not survive backend restart.
- Cancellation is cooperative.
- External providers influence runtime reliability based on network and credential state.
- The realtime WebSocket is production-hardened for the supported single-user,
  single-replica deployment: durable ordered events, reconnect replay,
  bounded queues, heartbeats, origin checks, and idempotent commands. A
  load-balanced deployment needs sticky sessions or a shared event broker and
  shared metrics/tracing before it is supported.

## Distribution Notes

Current scripts optimize for local execution, not a standalone server distribution bundle. Use `start_on_windows.ps1` for the supported Windows workflow or the manual commands in `runtime/startup.md`.

There is no first-class container, Linux/macOS launcher, hosted deployment
manifest, or durable external job worker in this checkout. Background jobs and
conversation-run event fanout remain process-local, while run events are
persisted for replay during the process lifetime.
