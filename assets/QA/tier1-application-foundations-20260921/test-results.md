# Tier 1 automated test results

Date: 2026-09-21
Revision: `c615c5799e1d5fb01e0af0eccaab5c6490d554c0`

## Backend foundation suite

Targeted app-factory, chat contract, conversation, realtime, job, run
lifecycle, runtime Settings, credential, model-library, structured probe,
context-profile, and model-settings tests ran with the repository venv and
canonical `runtimes/cache` pytest paths.

Result: **105 passed, 2 warnings, 12.98s**.

The warnings were dependency deprecations from Starlette/httpx and
`google.genai`; neither was a test failure.

## Frontend regression suite

```powershell
& '.\runtimes\nodejs\npm.cmd' --prefix '.\app\client' run test -- --watch=false --browsers=ChromeHeadlessNoGpu
```

Result: **248 passed**. Angular reported the existing Karma builder and HTML
sanitizer warnings; no test failed.

## Browser E2E subset

The state-persistence and app-shell subset ran against the launched local
services with an isolated pytest base/cache path.

Result: **11 passed, 2 failed, 1 deselected, 28.27s**.

Failed assertions:

1. `test_refresh_same_tab_restores_chat_and_map_state[chromium]` restored the
   logical chat/map state but did not expose `.maplibregl-canvas` under
   `ChromeHeadlessNoGpu`. Classified under `T1-02` as a renderer/fixture
   boundary pending WebGL-capable retest.
2. `TestChatFlow.test_settings_page_opens_from_toolbar[chromium]` requested
   `role=tab` for the Settings sidebar, while the current accessible DOM uses
   buttons. Classified under `T1-09` as test-contract drift; desktop browser
   proof passed.

The run was not converted into a blanket E2E failure: exact failure boundaries
and passing subtests are retained in the Tier 1 ledger.
