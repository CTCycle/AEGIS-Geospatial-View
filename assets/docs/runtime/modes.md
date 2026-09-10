# Runtime Modes

Last updated: 2026-09-10

## Supported Modes

### Local Development

- Backend: FastAPI
- Frontend: Angular dev or preview server
- Primary launcher: `start_on_windows.ps1`
- Portable runtimes are expected under `runtimes/`

### Automated Test Runtime

- Orchestrator: `app/tests/run_tests.bat`
- Starts backend and frontend, then runs pytest and browser validation

### Agent Loop Rollout

`agent_execution.agent_loop_mode` controls the temporary migration boundary:

- `legacy` (default) retains the parser/planner compatibility path.
- `shadow` computes native exposure without external model, provider, evidence,
  or map execution.
- `native_v2` runs the typed route-first native loop. Direct map responses remain
  `prepared_unverified` until a realtime browser acknowledgment path is used.

### Browser Validation Tooling

- The frontend pins Node.js `22.23.1` in `app/client/.nvmrc`.
- Codex browser automation requires Node.js `>=22.22.0`
- When the active `node` is older, use available browser tooling or point `NODE_REPL_NODE_PATH` at a compatible runtime

## Not Implemented

- No first-class Docker deployment files
- No Linux or macOS launcher is included
- No standalone production distribution artifact is maintained; deployment is
  currently a local Windows launcher/manual-start workflow.
