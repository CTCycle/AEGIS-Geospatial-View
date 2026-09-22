# T1-02 validation report

Last updated: 2026-09-22

## Result

`PASS` for frontend tab-local state on the tested working tree. Persisted chat
draft, overlay visibility, and opacity survived same-tab reload; separate tabs
kept independent drafts. TTL, corrupted-state recovery, stale overlay IDs,
route history, and missing-snapshot recovery also passed.

## Source and environment boundary

- Branch: `develop`
- Base commit: `8375fe071823e7f844f6bb125d86d6ebf36b3110`
- Source changes: uncommitted working-tree changes; exact tested source-file
  SHA-256 values are in [`source-sha256.txt`](source-sha256.txt).
- OS: Windows
- Browser: system Chrome channel, headed Playwright run; Karma used
  `ChromeHeadlessNoGpu`.
- Frontend: Angular development server at `127.0.0.1:4512`.
- Backend: standard test runner at `127.0.0.1:7059`; SQLite data was isolated
  at `runtimes/cache/test-runtime/t1-02-browser-20260922`.

## Executed checks

| Check | Result | Coverage |
| --- | --- | --- |
| Focused Angular Karma suite | `PASS`, 90/90 | App-state schema/store, expiry and corruption rules, overlay restoration, and geospatial-page synchronization. |
| `app/tests/e2e/test_chat_state_persistence.py` | `PASS`, 8/8 | Same-tab chat/map restoration, cross-tab isolation, route back/forward, unknown route, missing conversation, corrupt/expired state, and stale overlay recovery. |

The headed browser case changed the overlay to unchecked and opacity to 34%,
reloaded the page, then verified the persisted state and visible controls. The
saved capture is [`t1-02-restored-map-state.png`](<screenshots/__test_refresh_same_tab_restores_chat_and_map_state[chromium]/t1-02-restored-map-state.png>).

## Boundary and hand-off

The 2026-09-21 `loop-dev` headless-canvas failure remains historical evidence;
the current T1-02 reload and control-state boundary passed in headed Chrome.
The test fixture returns transparent map tiles, so this result does not claim
provider pixels, live geospatial rendering, or map-render acknowledgement.
Those remain separate campaign gates.

Continue with `T1-03` conversation lifecycle and history. Tier 1 remains
`PARTIAL` until its other incomplete slices are resolved.
