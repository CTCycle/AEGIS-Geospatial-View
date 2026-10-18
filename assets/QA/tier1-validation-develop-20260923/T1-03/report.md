# T1-03 validation report

Last updated: 2026-09-23

## Result

`PASS` for conversation history search, paging, selection, hydration, isolation, and stale-ID recovery. A focused transcript spacing defect found during hydration was repaired and visually rechecked.

## Source and environment boundary

- Branch: `develop`
- Starting commit: `35d04f8399d0166d1a134ad9f45931bc15efda91`, clean and equal to `origin/develop` at task start.
- Tested source delta: only `app/client/src/app/pages/geospatial-page.component.css`; its SHA-256 is recorded in [`source-sha256.txt`](source-sha256.txt).
- T1-02 provenance: its 2026-09-22 test remains scoped to base `8375fe071823e7f844f6bb125d86d6ebf36b3110` plus the five fingerprinted working-tree files. Those exact source hashes are now committed at starting HEAD `35d04f8`; this continuation does not move the historical T1-02 test boundary.
- OS: Windows
- Launcher: official `start_on_windows.ps1 -Action Launch` workflow.
- Frontend/backend: Angular development server `127.0.0.1:4512`, backend `127.0.0.1:7059`.
- Isolated data: `runtimes/cache/test-runtime/t1-03-20260923`; no normal user database was used.
- Browser: Codex in-app Browser. Provider/model execution and live map rendering were not exercised.

## Checks

| Check | Result | Coverage |
| --- | --- | --- |
| Conversation API and history repository suites | `PASS`, 9/9 | Conversation snapshot/list/search and history repository contracts. Two upstream deprecation warnings. |
| Geospatial page Karma suite | `PASS`, 47/47 | Existing component regression suite after the transcript spacing repair. |
| In-app Browser history search and pagination | `PASS` | Search isolated Conversation 15; first page contained 30 entries; next page produced 32 unique entries with no duplicates. |
| In-app Browser selection and isolation | `PASS` | Conversation 31 and 30 hydrated their distinct user/assistant markers without cross-conversation content. |
| Stale conversation recovery | `PASS` | Deleted synthetic row returned API `404`; selecting its cached history row cleared the chat and previous transcript content. |
| Hydrated transcript layout | `PASS` after repair | First user message no longer overlaps the floating History/action controls. |

Raw test output is in [`backend-tests.log`](backend-tests.log) and [`frontend-tests.log`](frontend-tests.log). Fixture identities are recorded in [`seed.json`](seed.json); browser observations and the visual-evidence limitation are in [`browser-evidence.md`](browser-evidence.md). Task-owned process and cache cleanup is recorded in [`process-cleanup.log`](process-cleanup.log).

## Focused repair

The transcript began too close to the panel top while its controls were absolutely positioned. On the initial browser capture, the first right-aligned user message intersected the action bar. Increasing `.chat-transcript` top padding from `0.85rem` to `3.25rem` reserves that control area. The 47-case component suite passed, and the updated layout was visually confirmed in the in-app Browser.

## Gate roll-up and hand-off

T1-03 is `PASS` on its local test and browser evidence. Tier 1 is `PARTIAL` at 8 `PASS` / 4 `PARTIAL`; the 68-slice campaign is `PARTIAL` at 13 `PASS` / 4 `PARTIAL` / 51 `UNRUN`. The exact pushed-head hosted-CI run is a separate `FAIL`: the backend unit job stopped before collecting tests because its command references missing path `app/tests/unit/services/search`. The other three jobs passed. See [`hosted-ci.md`](hosted-ci.md); do not fold this workflow failure into the T1-03 local result. The next actionable slice is `T1-06`.
