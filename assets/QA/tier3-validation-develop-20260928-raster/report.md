# Raster descriptor and renderer-boundary validation

Date: 2026-09-28
Branch: `develop`
Starting source: `4225cd6e710dfd50b98955f81896afaa215a7326`
Runtime: isolated `runtimes/cache/test-runtime/validation-20260924-exact-lane`
Services: backend `127.0.0.1:7059`, frontend `127.0.0.1:4512`

## Scope and result

The actionable slice was the public-raster descriptor boundary behind
`ISSUE-002`. The direct layer-feature API was losing catalog metadata before
calling descriptor providers. That made the ESA provider return `serviceUrl:
null` and left the client WMTS renderer without a usable source URL.

The API now forwards the manifest's public `metadata` object in the
`ProviderRequest`. The focused regression confirms the ESA service URL and
layer ID are preserved. The current API also returns the existing FEMA export
descriptor unchanged. This narrow descriptor/renderer-contract slice is
`PASS`.

## Checks executed

- Strict production layer audit: 86 manifests, 0 errors, 0 warnings; FEMA,
  ESA, raster-tile, and WMTS coverage are present.
- Backend focused suite covering geospatial API contracts, regional providers,
  render completion, and map-plan handling: **76 passed**, 2 existing dependency
  deprecation warnings.
- Changed-file Ruff check with isolated `RUFF_CACHE_DIR`: **passed**.
- ChromeHeadlessNoGpu geospatial browser module: **6/6 passed**. This is
  controlled client-renderer coverage, not live public-provider proof.
- Current isolated API recheck: ESA returned `wmts` with the Terrascope URL,
  `WORLDCOVER_2021_MAP`, and `EPSG:3857`; FEMA returned `raster-tile` with the
  NFHL export template. See [api-response.json](api-response.json).

## Exact-lane and browser boundary

The exact configured `opencode-go / deepseek-v4.1-flash` probe was attempted
after restarting the isolated backend. It returned `Native tool probe failed`.
Refreshing the user-supplied credential in the isolated runtime was rejected
by the provider catalog with HTTP 401. The provider/model was not substituted;
the sanitized result is in [provider-probe.json](provider-probe.json).

The in-app browser was used first. It displayed the saved New Orleans FEMA
conversation's existing failure state: retrieval metadata was present, but the
assistant reported `render_failed` with the overlay source absent and no
`map.render_ack`. That is historical saved evidence, not a new live exact-lane
run. No live raster `PASS` is claimed.

## Remaining limitation

`ISSUE-002`, `maps.raster-overlays`, and the FEMA-dependent composition and
retention checks remain `PARTIAL`/blocked at the real public MapLibre
source-load and acknowledgement boundary. The repaired descriptor path is
validated, but a fresh live browser run requires a working exact provider lane
and successful public source loading. T3-07 through T3-18 remain `UNRUN` unless
their stated prerequisites are opened; this focused contract check does not
silently consume those campaign slices.
