# Tier 3 vector composition validation follow-up

Run date: 2026-09-26.

## Decision

This follow-up covers two adjacent Tier 3 slices:

- `T3-05` live Census TIGERweb hydrography rendering: **PASS**.
- `T3-06` renderable vector composition and selective removal: **PASS**.

The exact configured `opencode-go / deepseek-v4.1-flash` lane was retained
throughout. No provider or model fallback was used.

## Source and runtime

- Branch: `develop`.
- Tested source: `develop@d3f719465a7c185cd7b5035b965083b1c602b369`.
- Backend/frontend: `127.0.0.1:7059` / `127.0.0.1:4512`.
- Isolated data root: `runtimes/cache/test-runtime/validation-20260924-exact-lane`.
- Browser: Codex in-app Browser at `http://127.0.0.1:4512/`.
- The Settings native tool probe returned `Verified` / `Native tool probe
  passed` before the live requests.

## Defect found and fixed

The first composition attempt exposed a completion-validation defect. The
rendered Census overlay was retained while the current USGS overlay was added,
but `_native_temporal_scope_applied` required every overlay instance to carry
the current temporal mode. Static retained overlays do not need temporal
metadata, so the backend rejected a browser-visible map whose two sources,
layers, and features were already valid.

The fix in `app/server/services/agent/completion.py` evaluates only overlay
instances with explicit `temporal_mode` or `time_mode` metadata and still
requires at least one temporal instance. The regression test
`test_temporal_scope_ignores_static_overlay_retained_during_current_update`
preserves the fail-closed behavior when temporal evidence is absent while
allowing a current overlay to coexist with a retained static overlay.

## Browser-authoritative evidence

### T3-05: standalone Census vector overlay

Request: `Show rivers and water features around Seattle, Washington.`

The browser visibly rendered the Seattle OSM map and the Census TIGERweb
Hydrography overlay. The transcript reported 13 returned water features and a
passed render check with 15 features rendered in view. The layer panel showed
`1 of 1 visible`; the legend and attribution identified Census TIGERweb, and
MapLibre attribution was visible. The transcript also preserved the provider's
partial-reliability note and the fallback viewport note rather than claiming
stronger coverage than the evidence supported.

### T3-06: composition and selective removal

Request: `Add active USGS water gauges around Seattle, Washington.`

The update retained the Census overlay while rendering the USGS response. The
browser reported two active gauges, showed both overlays at `2 of 2 visible`,
and displayed the two clustered gauge points together with the hydrography
layer. The final render check passed with both sources and layers present and
13 + 2 features rendered; the viewport was fitted to the combined evidence
extent; U.S. Census Bureau TIGERweb and U.S. Geological Survey attributions
were both visible.

Request: `Remove the USGS water gauges but keep the Census hydrography layer.`

The browser reported `Map state update verified`. The USGS overlay disappeared
while the Census layer remained visible and attributed at `1 of 1 visible`.
This proves vector retention/removal for renderable overlays; it does not prove
retention of an overlay whose source failed to load.

The browser-control surface exposed the screenshots inline but did not expose
a filesystem export path. The visual evidence is recorded from those inline
captures and the accessibility tree in
[browser-evidence.md](browser-evidence.md).

## Focused checks

| Check | Result |
| --- | --- |
| `test_render_completion.py` and `test_map_plan_service.py` | `34 passed` |
| Ruff on changed Python files | `All checks passed` |
| `git diff --check` | Passed; only normal LF-to-CRLF working-copy warnings were reported |

## Remaining boundaries

The public FEMA recheck remains the existing source-load boundary: FEMA data
was retrieved, but the raster source failed to load in MapLibre, so no FEMA
layer was acknowledged. ESA has the same unresolved source-loading class, and
NOAA remains the exact-lane non-renderable/tool-validation `BLOCKED` boundary.
Those conditions remain separate from the passing vector composition slice.

`T3-07` through `T3-18` remain `UNRUN`. Tier 4A, Tier 4B, and Tier 5 remain
`UNRUN`. Tier 0 `T0-04` remains `PARTIAL` solely because the safe historical
startup timing comparator is unavailable. Credentialed/local source access and
the broader route/provider/matrix claims remain partial or blocked.

## Cleanup

The path-verified task-owned backend PID `26880`, frontend PID `21544`, and
their launcher/process-tree children (`29128`, `35632`, `23148`, and `10740`)
were stopped after the browser run. Ports `4512`, `7059`, and `9876` were
verified free. The isolated runtime may be retained for evidence review; the
temporary Codex-created browser tab is not a durable deliverable.
