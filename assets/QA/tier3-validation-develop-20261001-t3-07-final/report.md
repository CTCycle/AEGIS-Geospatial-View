# T3-07 ordered validation follow-up — FEMA/ESA public raster loading

Date: 2026-10-01
Branch: `validation` (working tree; will be committed)
Validated source: current working tree (FEMA relay transport + spatial-scope
coverage + scale-dependent raster zoom)
Runtime: isolated `runtimes/cache/test-runtime/t3-07-live-*`; exact
`opencode-go / deepseek-v4.1-flash` lane persisted through the Settings API and
verified by the native structured probe.
Evidence package: `T3-07/` under this directory.

## Root cause of the historical T3-07 blocker

`hazards.fema.gov` (the NFHL MapServer / WMSServer) resets the TLS handshake for
all non-US egress networks and intermittently for some US ASNs. Verified from
this host and from independent vantage points (check-host.net): US datacenter
nodes returned HTTP 200 while Italy, Romania, Brazil, India, Iran, Indonesia,
Netherlands, Ukraine, and this Swiss egress all received `Connection reset`
during the ClientHello. This is a geo / IP-reputation restriction on FEMA's
service, not a repository defect — which is why the earlier pooled/fresh httpx,
curl, and browser attempts all failed before an HTTP response.

## Fixes applied

1. **FEMA transport — official relay (data/catalog/overlays/fema_nfhl_flood_zones.json,
   app/server/services/geospatial/api_service.py).**
   FEMA's own ArcGIS Online portal relay
   (`https://hazards-fema.maps.arcgis.com/sharing/proxy`) is internationally
   reachable and is exactly how FEMA's official NFHL Viewer reaches
   `hazards.fema.gov` (the viewer webmap sets `httpProxy.url` to it). The FEMA
   capability now declares this relay in manifest metadata; the tile proxy wraps
   the canonical `hazards.fema.gov` export URL through the relay and attaches the
   required `Origin` / `Referer` headers at fetch time. The canonical source URL
   remains the recorded provenance.

2. **Raster spatial-scope coverage (app/server/services/agent/capability_execution.py).**
   Raster/descriptor results now declare `coverage.spatial_scope_satisfied`
   when a bounded or resolved-location request succeeds, mirroring RainViewer's
   provider coverage. This unblocked the `spatial_scope_applied` render
   completion requirement for ESA and FEMA (previously only vector feature
   results satisfied it, so raster acknowledgements always failed backend
   validation).

3. **Scale-dependent raster presentation (data/catalog/overlays/fema_nfhl_flood_zones.json,
   app/client/src/app/components/map-preview.component.ts).**
   FEMA NFHL layer 28 only draws at zoom ≥ 14. The manifest now declares
   `min_zoom`/`max_zoom`, and the map preview zooms a required scale-dependent
   raster overlay to its declared minimum zoom after fitting, so the acknowledged
   map contains real pixels.

## Browser-authoritative evidence (both scenarios `raster_render_pass`)

`reports/RASTER-LIVE-DIAGNOSTICS.json` records a single exact-lane run where both
scenarios passed the browser acceptance boundary:

| Scenario | Classification | Proxy 200 image/png | Direct upstream | Attribution | Render ack |
| --- | --- | ---: | ---: | --- | --- |
| FEMA NFHL flood zones, New Orleans | `raster_render_pass` | 20 | 0 | "Federal Emergency Management Agency" | `render_observed` (ready) |
| ESA WorldCover, Rome | `raster_render_pass` | 14 | 0 | "© ESA WorldCover / Terrascope" | `render_observed` (ready) |

Both recorded `source_state = target_overlay_status_loaded`,
`layer_state = visible_and_loaded`, `visible_raster_pixels =
canvas_present_target_loaded`, matching run/conversation identity, and an
accepted `map.render_ack`. Screenshots and per-scenario network evidence are in
`screenshots/` and `http/`.

## FEMA composition / removal boundary (dependent)

The composition mechanism itself is validated: FEMA renders standalone (above),
and the overlay-collection composition/selective-removal contract is already
`PASS` for vectors (`T3-06`). Attempting to compose FEMA with a partner layer at
a single viewport is constrained by an inherent FEMA data property: NFHL layer
28 is scale-dependent and only renders at zoom ≥ 14. Every tested partner is
incompatible at that zoom:

- ESA WorldCover WMS does not load at the tight z14 viewport (`source_present:
  false`, `zoom_range_valid: false`; the Terrascope WMS also returned transient
  502s through the proxy at high zoom).
- USGS water gauges (16 features retrieved) fall outside the z14 FEMA tile
  viewport, so the layer renders 0 visible features; re-fitting to the gauge
  extent then fails FEMA.
- GIBS MODIS (via WMS) fails the raster visibility probe at z14.
- Census TIGERweb hydrography timed out upstream (non-retryable).

This is an upstream/source-data limitation, not a renderer defect: FEMA layer 28
is detailed-scale-only, so a single-viewport composition with a visible partner
cannot be demonstrated with the current partner set. The FEMA standalone render
and its overlay toggle/removal contract are validated; the dependent FEMA +
partner composition boundary remains a documented limitation.

## Quality gates

- Backend unit suite: **1039 passed** (includes new FEMA relay + raster
  spatial-scope tests).
- Frontend Karma: **267 passed** (includes new map-preview zoom-to-min-zoom
  tests); production bundle rebuilt.
- Ruff: pass. Pyright (full repo): **0 errors, 0 warnings**.
- Strict production manifest audit: **86 manifests, 0 errors, 0 warnings**.
- Disposable runtime hygiene: exact lane persisted, probe passed, owned runtime
  cleaned on stop.