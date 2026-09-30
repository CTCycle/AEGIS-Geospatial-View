# Configuration

Last updated: 2026-09-30

## Environment file

The primary runtime environment file is `settings/.env`. If it is missing,
startup creates it from `settings/.env.example`; an existing file is never
overwritten. The generated file remains local.

Common keys include:

- `AEGIS_DATA_DIR` (optional; defaults to `data/runtime`; relative
  values are resolved from the repository root)
- `SQLITE_LOCK_TIMEOUT` (positive seconds; defaults to `60`)
- `FASTAPI_HOST`
- `FASTAPI_PORT`
- `UI_HOST`
- `UI_PORT`
- `RELOAD`
- `BACKEND_LOGS_VISIBLE`
- `REALTIME_ALLOW_MISSING_ORIGIN` (default `false`; test-only exception for
  non-browser clients)
- `AEGIS_ALLOW_RESTRICTED_SOURCES` (default `false`; explicitly opts the
  deployment into public capabilities marked with the
  `restricted_usage_opt_in` runtime policy)

The SQLite database path is always derived as:

```text
<AEGIS_DATA_DIR or data/runtime>/database.db
```

`SQLITE_LOCK_TIMEOUT` controls how long startup and the explicit launcher
initialization action wait for the adjacent SQLite migration lock. It does not
change SQL transaction timeouts or database durability settings.

## Runtime configuration

`settings/.env` is limited to bootstrap and deployment values: data-root and
database-lock settings, service hosts and ports, reload behavior, and other
process-level switches. It is not the source of application-editable runtime
blocks.

Application runtime settings are validated typed blocks stored in the SQLite
`application_runtime_settings` row and exposed through
`GET/PATCH /api/settings/runtime`. The blocks cover Nominatim, geospatial
bounds, map defaults, job polling, chat defaults, Open-Meteo, Overpass,
RainViewer, NASA GIBS request tuning, and the native agent execution policy.
The PATCH body may contain one or more changed blocks; each block contains only
the changed fields, and the server merges and validates the patch before one
atomic commit. Responses never contain credentials or secret values and identify
when a restart is required.

Older installations with `settings/configurations.json` are migrated once at
startup: the legacy file is validated, the SQLite row is committed, and only
then is the file retired. Invalid legacy data fails visibly and remains in
place for correction; SQLite is not silently replaced with defaults.

The `agent_execution` runtime block owns the complete native-agent deadline
policy and exposes 31 editable fields. Defaults are grouped as follows:

- Execution budgets: `initial_run_seconds=90`, `simple_seconds=150`,
  `complex_seconds=300`, `simple_max_model_calls=4`,
  `complex_max_model_calls=10`, `simple_max_tool_calls=6`,
  `complex_max_tool_calls=20`, `simple_max_state_transitions=32`,
  `complex_max_state_transitions=64`, and `max_iterations=12`.
- Failure recovery: `max_render_attempts=3`, `max_discovery_attempts=2`,
  `max_no_progress_corrections=2`, `max_consecutive_tool_failures=3`,
  `max_same_failed_fingerprint=2`, `max_route_corrections=1`, and
  `max_validation_corrections=2`.
- Timeouts and retries, in seconds unless noted: `context_assembly_seconds=5`,
  `native_model_call_seconds=60`, `tool_execution_seconds=45`,
  `tool_absolute_seconds=90`, `map_assembly_seconds=20`,
  `persistence_seconds=5`, `render_ack_seconds=90`,
  `model_max_attempts=2`, `provider_max_attempts=2`,
  `retry_backoff_base_seconds=0.25`, `retry_backoff_max_seconds=2`, and
  `provider_request_seconds=10`.
- Advanced limits: `max_parallel_tool_calls=8` and
  `max_tool_result_chars=4096`.

Smaller provider/model limits still win. These values are one typed policy block
rather than independent environment knobs. Provider request settings are
injected into the same runtime provider policy, and there is no
legacy/shadow execution-mode setting.

Agent-only PATCH updates are hot-applied for future work: each new agent run
reads the latest saved policy and receives an immutable execution-policy
snapshot. The snapshot is retained in the run checkpoint, so active and
render-suspended runs keep the policy with which they started, including model,
tool, provider, and render timeouts. Agent-only updates return
`restart_required=false`; changes to other runtime blocks still require a
restart, and a mixed patch reports that requirement.

Model provider API keys are entered through Settings and stored as encrypted
database records. They are not database connection settings.

The model provider contract accepts exactly `openai`, `google`, `deepseek`,
`opencode`, `opencode-go`, and `ollama`. Unknown, stale, case-variant, and
aliased provider IDs are rejected; a provider or model failure never selects a
different provider or model automatically.

## Local profile

The source template is `settings/.env.example`. The Windows launcher uses the
configured hosts and ports for the local web workflow. `BACKEND_LOGS_VISIBLE`
controls whether backend logs use a visible terminal.
