# Tier 1 application-foundations baseline

Date: 2026-09-21
Branch: `loop-dev`
Commit: `c615c5799e1d5fb01e0af0eccaab5c6490d554c0`
Launcher: `start_on_windows.ps1 -Action Launch`
Overall status: `PARTIAL`

## Outcome

The first application-foundations tier is now represented in the durable
validation ledger. The current revision has strong local contract evidence but
is not Tier 1 complete: six of twelve slices remain `PARTIAL` because required
boundaries were either exposed by a renderer/test environment or were not
opened in this campaign.

| Result | Count |
| --- | ---: |
| `PASS` | 6 |
| `PARTIAL` | 6 |
| `FAIL` | 0 |
| `BLOCKED` | 0 |
| `UNKNOWN` | 0 |
| `UNTESTED` | 0 |

The machine-readable row data is in [`ledger.json`](ledger.json), with the
compact human view in [`ledger.md`](ledger.md).

## Evidence

- The official launcher started backend port 7059 and frontend port 4512.
- The targeted backend foundation suite reported **105 passed** with two
  dependency deprecation warnings.
- The full Angular client suite reported **248 passed**.
- The bounded browser E2E subset reported **11 passed, 2 failed, 1
  deselected**. The failures are retained and classified below.
- The Codex in-app browser verified route fallback, the below-minimum desktop
  gate, all seven Settings sections, history search, panel state across reload,
  and a safe non-secret credential save/mask/clear/reload flow.

## Partial boundaries

### `T1-02` — restored logical state without headless MapLibre canvas

`test_refresh_same_tab_restores_chat_and_map_state` restored the seeded
transcript, draft, location, overlay, and alert state. The assertion for
`.maplibregl-canvas` then failed under `ChromeHeadlessNoGpu`. The first
incorrect boundary is automated renderer admission/fixture, not restored
logical state. Retest in a WebGL-capable browser or repair the fixture before
promoting the renderer portion.

### `T1-09` — stale Settings role assertion

`TestChatFlow.test_settings_page_opens_from_toolbar` failed because it requests
Settings controls with `role=tab`. The current accessible DOM exposes the seven
sections as buttons, and the desktop-width browser verified all seven URLs and
content surfaces. Align the test with the current contract, then rerun dirty
draft/save/back behavior.

### Other incomplete slices

- `T1-03`: saved-conversation selection/hydration, pagination, and missing-ID
  browser recovery remain open.
- `T1-06`: the exact live `/api/chat/turn` `200/202/409/404/503` timing matrix
  remains open; old 409 evidence is not promoted to a current failure.
- `T1-07`: mounted job endpoints, unknown-job behavior, and process-shutdown
  semantics remain open.
- `T1-10`: controlled unreadable-credential and explicit API-failure fixtures
  remain open. The safe fixture was cleared and was not a real secret.

## Preservation boundary

No application source or test was changed. No real credential, provider secret,
chain-of-thought, or unsafe raw payload was recorded. Existing conversations
were read for history search only; none was deleted or rewritten. The browser
could display screenshots inline, but this tooling did not export a local
binary screenshot, so this package claims rendered observations and not a
checked-in PNG.

## Next exact actions

1. Retest `T1-02` with WebGL-capable evidence.
2. Align the Settings E2E locator and rerun `T1-09` with a dirty draft.
3. Execute saved-conversation hydration and missing-ID recovery for `T1-03`.
4. Run the isolated live HTTP matrix for `T1-06` before changing `ISSUE-003`.
5. Add mounted job API/shutdown evidence for `T1-07`.
6. Add controlled unreadable/API-failure credential fixtures for `T1-10`.
