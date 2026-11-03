# Configuration

Last updated: 2026-11-03

## Environment file

The primary runtime environment file is `settings/.env`. If it is missing,
startup creates it from `settings/.env.example`; an existing file is never
overwritten. The generated file remains local.

Common keys include:

- `AEGIS_DATA_DIR` (optional; defaults to `data/runtime`; relative
  values are resolved from the repository root)
- `FASTAPI_HOST`
- `FASTAPI_PORT`
- `UI_HOST` (Angular dev server only)
- `UI_PORT` (Angular dev server only)
- `RELOAD`
- `BACKEND_LOGS_VISIBLE`
- `AEGIS_LOG_LEVEL` (defaults to `INFO`; set to `DEBUG` for successful HTTP access and detailed application diagnostics; accepts `WARNING` and `ERROR`)
- `REALTIME_ALLOW_MISSING_ORIGIN` (default `false`; test-only exception for
  non-browser clients)
- `AEGIS_ALLOW_RESTRICTED_SOURCES` (default `false`; explicitly opts the
  deployment into public capabilities marked with the
  `restricted_usage_opt_in` runtime policy)

The data root contains the independent database configuration and, by default,
the SQLite file:

```text
<AEGIS_DATA_DIR or data/runtime>/database-settings.json
<AEGIS_DATA_DIR or data/runtime>/database.db
```

`database-settings.json` is the only source for the selected database backend,
database path, and SQLite migration-lock timeout. It is written atomically,
validated on load, and has a `.bak` recovery copy. If neither the file nor its
recovery copy exists, built-in defaults select SQLite at `database.db` with a
60-second migration-lock timeout. The file is never populated from environment
variables.

## Runtime configuration

`settings/.env` is limited to bootstrap and deployment values: the general
application data root, service hosts and ports, reload behavior, and other
process-level switches. It is not the source of database connection settings
or application-editable runtime blocks.

Application runtime settings are validated typed blocks stored in the SQLite
`application_runtime_settings` row and exposed through
`GET/PATCH /api/settings/runtime`. The blocks cover Nominatim, geospatial
bounds, map defaults, conversation-run status polling, chat defaults, Open-Meteo, Overpass,
RainViewer, NASA GIBS request tuning, and the native agent execution policy.
The PATCH body may contain one or more changed blocks; each block contains only
the changed fields, and the server merges and validates the patch before one
atomic commit. Responses never contain credentials or secret values and identify
when a restart is required.

When a database has no runtime-settings row, initialization seeds built-in
defaults. Runtime settings are never imported from or read from a JSON fallback.

The `agent_execution` runtime block owns the complete native-agent deadline
policy and exposes 32 editable fields. Defaults are grouped as follows:

- Execution budgets: `initial_run_seconds=300`, `simple_seconds=450`,
  `complex_seconds=600`, `simple_max_model_calls=12`,
  `complex_max_model_calls=30`, `simple_max_tool_calls=20`,
  `complex_max_tool_calls=60`, `simple_max_state_transitions=100`,
  `complex_max_state_transitions=200`, and `max_iterations=40`.
- Failure recovery: `max_render_attempts=5`, `max_discovery_attempts=4`,
  `max_no_progress_corrections=3`, `max_unproductive_steps=5`,
  `max_consecutive_tool_failures=5`, `max_same_failed_fingerprint=3`,
  `max_route_corrections=2`, and `max_validation_corrections=4` (counted once
  per model step, not per call in a parallel batch). After
  `max_unproductive_steps` consecutive tool steps that establish nothing new
  the model receives a corrective observation; two more end the run as
  `no_progress` with the gathered evidence summarized.
- Timeouts and retries, in seconds unless noted: `context_assembly_seconds=5`,
  `native_model_call_seconds=120`, `tool_execution_seconds=90`,
  `tool_absolute_seconds=120`, `map_assembly_seconds=20`,
  `persistence_seconds=5`, `render_ack_seconds=120`,
  `model_max_attempts=3`, `provider_max_attempts=3`,
  `retry_backoff_base_seconds=0.25`, `retry_backoff_max_seconds=2`, and
  `provider_request_seconds=30`.
- Advanced limits: `max_parallel_tool_calls=8`,
  `max_tool_result_chars=16384`, and `max_output_tokens=32768` (global
  per-call output cap for every model, clamped to the model's published
  maximum). Reasoning models spend this budget on thinking first; an empty
  reply that hit the cap fails the run with a message pointing to this setting.

Smaller provider/model limits still win. Every cap above is editable in Settings
and the ceilings are generous (for example 1000 iterations, 2000 tool calls,
3600 s per run, 600 s per tool call or render acknowledgement); only the
loop-safety guards (no-progress, repeated failures) stay deliberately modest. These values are one typed policy block
rather than independent environment knobs. Provider request settings are
injected into the same runtime provider policy.

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
