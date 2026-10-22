# Full validation pass — 2026-10-22

Tested: `develop@1a864a99` plus the uncommitted working tree (single-origin SPA serving, `/api/*` 404 guard, backend-origin WebSocket allowance, launcher/doc edits, and the fixes below). Isolated runtime: a copy of `data/` under `runtimes/cache/test-runtime` (database path rewritten; removed afterwards); one backend process serving the built SPA and API on 127.0.0.1:7059. The environment has **no agent model or credentials configured**, so every live model-lane scenario is BLOCKED (not substituted).

## Results

| Gate | Result |
| --- | --- |
| Ruff, strict Pyright | PASS (0 errors) |
| Backend unit + agent_benchmark | PASS 1,164 |
| Frontend production build, Karma | PASS (303/303) |
| Single-origin serving, real browser | PASS: SPA at `/`, `/settings`, `/geodata` deep links, `/api/missing` 404, real WebSocket accepted for a real conversation, 1024 px minimum-width guard shown at narrow width |
| Real-app journeys (in-app browser) | PASS: send prompt with no model creates a failed run surfaced in Tool activity (by design) and a "Needs attention" chip; Geodata catalog; Settings Database section showing the active isolated database |
| Playwright E2E (`app/tests/e2e`), final run | 59 passed, 2 failed, 26 skipped ([run log](e2e-run5.log)); earlier run on the same tree before fixes: 50/11/26 |

## Defects found and fixed

1. **Map intermittently disappeared on load (app defect, ~35% of cold loads in headless Chromium).** `candidate.resize()` at map `load` and the ResizeObserver resize could run before the WebGL drawing buffer synced; MapLibre 4.7.1 then permanently clamped the canvas to 0x0 and `hasRenderableCanvas` rejected the map with no visible message. Fix: `resizeMapToContainer` only resizes when the canvas no longer matches its container ([map-preview.component.ts](../../../app/client/src/app/components/map-preview.component.ts)); new Karma spec. Probe: 0/20 failures afterwards (was 6/20 and 4/10).
2. **Geospatial/cloud credential Clear sent a duplicate replacement PATCH after a failed save** (blur re-sent the failed draft before the Clear click). Fix: failed drafts are not resent on blur ([settings-page.component.ts](../../../app/client/src/app/pages/settings-page.component.ts)). The failing E2E test now passes.
3. **Ollama URL could not be saved on a fresh database with no agent model** (HTTP 4xx "Agent model provider and model name must both be configured."). Fix: the assignment is only validated when a model is set or the request changes it ([settings_service.py](../../../app/server/services/chat/settings_service.py)); new unit test; live PATCH now 200.
4. **Seven stale backend test doubles** (fixed earlier today, test-only).

## Stale E2E tests updated (correcting the earlier note)

The earlier note that the Settings model-card tests were stale was wrong: they pass (16/16) once the run is clean. The actually stale tests were: map tools and layer list now sit behind the "Map tools" toggle and "Expand" (`test_chat_state_persistence`, `test_orchestration_stress`, `test_documented_conversations`); persisted map state now includes `overlayOrder`; tab-local overlay preferences intentionally win over the snapshot when a page is restored (the stress test is renamed accordingly); run failures are reported in Tool activity, not as chat messages (`test_live_chat_smoke` degraded path); and the persistence tests now stub the realtime socket. The visual baseline test passed on this run; the earlier 886x594 vs 889x594 drift did not reproduce.

## Remaining failures and blockers

- `test_app_flow::test_chat_composer_visible_and_send_prompt`, `test_eea_raster_lifecycle`: BLOCKED, need a configured agent model (opencode-go lane). 26 skips: same cause or unavailable providers (503).
- Not covered: live provider/raster/route matrix, Tier 4B lanes, T5-11/T5-13 (no approved lanes), hosted CI for the new head, screen-reader review, the launcher interactive menu (only the equivalent backend command was run).

## Findings left open

- LOW: with no agent model configured, a chat send fails with the generic "The agent could not complete this request." and no chat message; the cause (no model selected) is visible only through the "Agent model: Needs attention" chip.
- Environment: `runtimes/cache/pytest-tmp` held 12 directories with orphaned ACLs that could not be deleted without admin rights; renamed to `pytest-tmp-locked-legacy` (gitignored).
