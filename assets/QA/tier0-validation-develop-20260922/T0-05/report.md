# T0-05 API composition and contract evidence

Status: `PASS`

## Boundary

- Branch: `develop`
- Starting HEAD: `7e8b10d58aebf21f194a74bcc2307f9d8e08f15c`
- Validated source commit: `afa608c8d5c53a34d0ce8da36e5fe5f47f689145`
- Validation source: working tree based on that exact HEAD.
- Python: `app/server/.venv/Scripts/python.exe` (Python 3.14)
- Isolated data: `runtimes/cache/test-runtime/tier0-validation-develop-20260922/T0-05/data`
- Pytest boundaries: `runtimes/cache/pytest` and
  `runtimes/cache/pytest-tmp/tier0-validation-develop-20260922-T0-05-final-retry`

## Coverage and result

The final command covered the complete `tests/unit/api` directory plus
`test_app_factory.py`, `test_openapi_schema.py`,
`test_runtime_settings_api.py`, `test_canonical_runtime_contract.py`, and
`test_sqlite_application_startup.py`.

Result: **44 passed, 2 warnings, 4.42 seconds**.

The slice proved:

- canonical health, chat, conversations, realtime, jobs, geospatial, and
  Settings composition with no shadow/preview/legacy router paths;
- runtime `app.openapi()` exact equality with `app/shared/openapi.json`;
- lifespan initialization ordering, state attachment, realtime close, job stop,
  run-lifecycle shutdown, and SQLite disposal;
- terminal `/api/chat/turn` `200 ChatTurnResponse`;
- accepted non-terminal `/api/chat/turn` `202 AgentRunAcceptedResponse` with
  `run_id`, `run_version`, state, status URL, realtime URL, and `terminal=false`;
- `409` only for a genuine `RunConflictError`, while missing conversations
  return `404` before orchestration;
- runtime Settings/model/structured-probe routes and credential masking;
- backend-only root redirect plus production root/assets/SPA fallback behavior.

The current contract tests intentionally do not claim live-provider availability
or complete browser/provider coverage. Those remain separate partial or unrun
campaign gates.

## Evidence

- [final API/composition log](api-focused-final-retry.log)
- [current 200/202/409 tests](../../../../app/tests/unit/api/test_chat_contracts.py)
- [OpenAPI parity test](../../../../app/tests/unit/test_openapi_schema.py)
