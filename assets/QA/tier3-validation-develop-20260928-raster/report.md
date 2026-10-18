# Raster descriptor and renderer-boundary validation

Date: 2026-09-28
Branch: `develop`
Descriptor source: `develop@9170f813`
Provider-readiness source: `develop@3de5619b`
Runtime: isolated descriptor checks plus canonical readiness recheck at
`app/resources`
Services: backend `127.0.0.1:7059`, frontend `127.0.0.1:4512` for the earlier
descriptor/browser boundary

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

The initial exact configured `opencode-go / deepseek-v4.1-flash` recheck
returned `Native tool probe failed`, and the isolated runtime's stored
credential refresh received HTTP 401. Further investigation found that the
canonical database held a different active credential. After moving the
healthy database to `app/resources/database.db` and saving the supplied
credential through the application settings endpoint, the final catalog
returned 30 models and the native probe passed with `parse_status=complete`.
See the [exact readiness report](opencode-go-readiness-report.md) and
[credential-path check](credential-path-check.json).

The provider/model was never substituted and no fallback was used. The
initial failure remains in [provider-probe.json](provider-probe.json) as
diagnostic history.

The in-app browser was used first. It displayed the saved New Orleans FEMA
conversation's existing failure state: retrieval metadata was present, but the
assistant reported `render_failed` with the overlay source absent and no
`map.render_ack`. That is historical saved evidence, not a new live exact-lane
run. No live raster `PASS` is claimed.

## Remaining limitation

`ISSUE-002`, `maps.raster-overlays`, and the FEMA-dependent composition and
retention checks remain `PARTIAL`/blocked at the real public MapLibre
source-load and acknowledgement boundary. The repaired descriptor path and
exact provider readiness are now validated, but a fresh live browser run still
requires successful public source loading. T3-07 through T3-18 remain `UNRUN`
unless their stated prerequisites are opened; this focused contract check does
not silently consume those campaign slices.
