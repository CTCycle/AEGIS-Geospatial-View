# Runtime Modes

Last updated: 2026-07-20

## Supported Modes

### Local Development

- Backend: FastAPI
- Frontend: Angular dev or preview server
- Primary launcher: `start_on_windows.ps1`
- Portable runtimes are expected under `runtimes/`

### Automated Test Runtime

- Orchestrator: `app/tests/run_tests.bat`
- Starts backend and frontend, then runs pytest and browser validation

### Browser Validation Tooling

- The frontend pins Node.js `22.23.1` in `app/client/.nvmrc`.
- Codex browser automation requires Node.js `>=22.22.0`
- When the active `node` is older, use available browser tooling or point `NODE_REPL_NODE_PATH` at a compatible runtime

## Not Implemented

- No first-class Docker deployment files
- No Linux or macOS launcher is included
