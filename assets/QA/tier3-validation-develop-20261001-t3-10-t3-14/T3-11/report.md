# T3-11 — NOAA CO-OPS water levels and CONUS radar (remaining NOAA family)

Date: 2026-10-01
Branch: `validation` (working tree)
Runtime: isolated `runtimes/cache/test-runtime/t3-07-live-*`; exact
`opencode-go / deepseek-v4.1-flash` lane persisted through the Settings API and
verified by the native structured probe.
Evidence package: `T3-11/` under this directory.

## Result

Both T3-11 sub-scenarios pass. NOAA CO-OPS coastal water-level stations render
as clustered points with NOAA attribution and an accepted `map.render_ack`, and
the NOAA radar raster now renders through the same-origin AEGIS tile proxy with
`NOAA/NCEP nowCOAST` attribution and an accepted `map.render_ack` — with zero
direct-upstream browser requests.

| Scenario | Classification | Overlay status | Attribution | Render ack | Direct upstream |
| --- | --- | --- | --- | --- | ---: |
| `t3_11_coops_charleston` | `map_render_pass` | `loaded` | "NOAA CO-OPS" | `render_observed` (ready) | 0 |
| `t3_11_radar_houston` | `map_render_pass` | `loaded` | "NOAA/NCEP nowCOAST" | `render_observed` (ready) | 0 |

The radar scenario recorded 48 same-origin proxy requests with
`proxy_capabilities_seen = [noaa_radar, osm_default]` and **0 direct-upstream
browser requests**, proving the radar raster now follows the same
manifest-backed tile-proxy transport as FEMA/ESA/GIBS/RainViewer.

## Root causes found and surgical fixes

The radar capability previously returned a direct upstream WMS `tileUrl` and was
not in `_BACKEND_RASTER_PROVIDERS`, so the browser fetched
`opengeo.ncep.noaa.gov` directly (and a backend 502 had been recorded
historically in the isolated environment). Two surgical fixes:

1. **`raster_tiles.py`**: added `noaa` to `_BACKEND_RASTER_PROVIDERS` so the
   render descriptor routes `noaa_radar` through the same-origin tile proxy.
2. **`noaa_radar.json`**: replaced the hardcoded full WMS query in
   `metadata.url_template` with a bare base URL plus structured WMS fields
   (`layer_id=conus_bref_qcd`, `crs=EPSG:3857`, `format=image/png`,
   `wms_version=1.3.0`, `style=""`, `wms_exceptions=...`) so
   `build_wms_get_map_url` constructs a single-parameter WMS GetMap.

The proxy tile path was verified directly
(`/api/geospatial/tiles/noaa_radar/{z}/{x}/{y}.png` returns `image/png`) before
the browser run.

## Quality gates

- Backend focused suites: **408 passed** (agent + geospatial unit suites,
  including the updated render-descriptor expectations and manifest audits).
- Ruff: pass. Pyright: **0 errors**.
- Disposable runtime hygiene: exact lane persisted, probe passed, owned runtime
  cleaned on stop.

## Remaining boundary

CO-OPS endpoint health remains `partial` (station observation availability
varies by station/product/datum), and radar coverage is CONUS-only by provider
design. Valid-empty/stale per-NOAA-response semantics were not separately
exercised this run.