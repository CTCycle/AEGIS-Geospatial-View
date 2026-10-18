# Runtime Modes

Last updated: 2026-09-15

## Supported Modes

### Local Development

- Backend: FastAPI
- Frontend: Angular dev or preview server
- Primary launcher: `start_on_windows.ps1`
- Portable runtimes are expected under `runtimes/`

### Automated Test Runtime

- Orchestrator: `app/tests/run_tests.bat`
- Starts backend and frontend, then runs pytest and browser validation

### Native Agent Harness

Chat and agent runs use one typed route-first native loop. Each run hydrates
the revisioned conversation state, compiles a goal/completion contract,
progressively exposes the small native tool surface, and iterates through
model decisions and bounded observations. Direct map responses remain
`prepared_unverified` until the realtime browser acknowledgment path is used;
realtime runs promote only after `map.render_ack` succeeds.

There is no runtime legacy/shadow/native switch. Compatibility code and
rollout-only preview modes were removed as part of the native consolidation.

### Browser Validation Tooling

- The frontend pins Node.js `22.23.1` in `app/client/.nvmrc`.
- Codex browser automation requires Node.js `>=22.22.0`
- When the active `node` is older, use available browser tooling or point `NODE_REPL_NODE_PATH` at a compatible runtime

## Not Implemented

- No first-class Docker deployment files
- No Linux or macOS launcher is included
- No standalone production distribution artifact is maintained; deployment is
  currently a local Windows launcher/manual-start workflow.
