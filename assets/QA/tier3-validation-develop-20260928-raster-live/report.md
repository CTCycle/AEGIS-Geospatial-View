# Tier 3 live public-raster validation

Date: 2026-09-28
Branch: `develop`
Tested source: `develop@14e94e09134b00c511138cf1cfe7567bd571d878`
Provider lane: `opencode-go / deepseek-v4.1-flash`
Runtime data root: `runtimes/cache/test-runtime/tier3-raster-live-20260928`

## Decision

**PARTIAL.** This run opened the next actionable Tier 3 slice (`T3-07`) and
revalidated the live public FEMA and ESA raster paths through the real
MapLibre browser. Both providers returned usable renderable raster evidence,
but neither public source loaded in the browser. The renderer correctly
failed closed and did not claim a map acknowledgement. The dependent FEMA
plus USGS composition and FEMA-retention scenarios remain **BLOCKED** because
the FEMA overlay never became a browser-visible rendered layer.

No implementation defect was found in this run. The current focused suite,
strict manifest audit, Ruff check, exact provider probe, and browser behavior
all agree that the remaining issue is the public source-load boundary.

## Validation evidence

- The official launcher started the isolated runtime and local services on
  ports 7059 and 4512.
- The exact structured probe returned `opencode-go`,
  `deepseek-v4.1-flash`, `status=passed`, and `parse_status=complete`.
- The current focused regression selection passed **96 tests** with two
  pre-existing deprecation warnings.
- The strict production layer audit reported **86 manifests, 0 errors, 0
  warnings**; Ruff passed.
- FEMA and ESA retrieval both returned `result_status=ok`,
  `map_eligibility=renderable`, and provider attribution. Their browser runs
  ended in `render_failed` because the MapLibre source was absent/unloadable.
- The USGS follow-up rendered only the gauge layer and the removal follow-up
  left the attributed basemap with no visible overlays. These runs prevent a
  false FEMA composition or retention claim.

Detailed browser observations and run identifiers are in
[browser-evidence.md](browser-evidence.md), [run-summary.json](run-summary.json),
and [provider-probe.json](provider-probe.json).

## Remaining boundaries

`ISSUE-002` remains open. Investigate the public FEMA export raster and ESA
WorldCover WMTS source-load failure at the browser/network/MapLibre boundary.
After a source and layer are visibly present and `map.render_ack` is received,
rerun the FEMA standalone, FEMA plus USGS composition, and FEMA retention
flows. Keep `T3-08` through `T3-18`, Tier 4A, Tier 4B, and Tier 5 unrun until
their own prerequisites are opened.

The task-owned backend/frontend processes were stopped and ports 4512, 7059,
and 9876 were verified free. The cloned runtime remains under the ignored
cache root for evidence review and was not staged.
