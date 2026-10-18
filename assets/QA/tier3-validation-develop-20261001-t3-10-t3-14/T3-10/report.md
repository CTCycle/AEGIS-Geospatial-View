# T3-10 — USGS Earthquakes live seismic overlay

Date: 2026-10-01
Branch: `validation` (working tree)
Validated source: current working tree (vector spatial/temporal scope coverage,
normalized point-feature intersection, valid-empty query-complete, undated
recent-aggregation routing)
Runtime: isolated `runtimes/cache/test-runtime/t3-07-live-*`; exact
`opencode-go / deepseek-v4.1-flash` lane persisted through the Settings API and
verified by the native structured probe (`parse_status=complete`).
Evidence package: `T3-10/` under this directory.

## Result

Both T3-10 scenarios pass the browser-authoritative acceptance boundary. The
overlay renders with visible clustered points, `U.S. Geological Survey`
attribution, and an accepted `map.render_ack`; the valid-empty scenario returns
an honest "no matching earthquakes" outcome with the map preserved and the run
completing normally.

| Scenario | Classification | Overlay status | Attribution | Render ack | Direct upstream |
| --- | --- | --- | --- | --- | ---: |
| `t3_10_earthquakes_tokyo` | `map_render_pass` | `loaded` | "U.S. Geological Survey" | `render_observed` (ready) | 0 |
| `t3_10_earthquakes_valid_empty` | `map_render_pass` | valid-empty | — | `render_observed` (ready) | 0 |

Both runs selected `usgs_earthquakes` (+ `osm_default` basemap), completed
normally, and recorded zero direct-upstream browser requests. Screenshots,
per-scenario network evidence, and run traces are in `screenshots/`, `http/`,
and `reports/`.

## Root causes found and surgical fixes

The first live run reached provider execution and prepared a candidate map, but
the browser ack was rejected at backend validation (`render_validation_failed`
on `temporal_scope_applied`/`spatial_scope_applied`). Four repo-owned defects
were reproduced and fixed:

1. **Vector evidence never declared spatial/temporal scope coverage.**
   `capability_execution.py` only stamped `coverage.spatial_scope_satisfied`
   for raster results and bbox-vector results; the render completion
   `data_checks` requires it for every renderable capability. Vector results
   over a resolved location (point/radius scope) and current/recent requests
   without an explicit dated range now stamp both flags, mirroring the raster
   contract.
2. **Bbox intersection rejected normalized point features.**
   The spatial-scope intersection check required a GeoJSON `geometry` field,
   but the USGS (and Open-Meteo, NOAA CO-OPS, Overpass) adapters return
   normalized `latitude`/`longitude` features. `_feature_spatial_geometry()`
   now accepts both shapes.
3. **Valid-empty results were not query-complete.**
   The completion assessment only accepts a `valid_empty` outcome when
   `coverage.query_complete` is set; the honest no-results boundary now
   declares it.
4. **Undated recent aggregation was not routed as current.**
   The model sometimes emitted `mode=historical, aggregation=recent,
   granularity=none`; `_normalize_recent_scope` only handled the
   granularity form. The aggregation form is now normalized to `current`,
   preserving the documented "undated recent intent matches current feed"
   contract.

Each fix is covered by a focused unit test (see `slice.json`).

## Quality gates

- Backend focused suites: **400 passed** (agent + geospatial unit suites
  including the new coverage/routing/valid-empty tests).
- Manifest contract + schema + layer auditor + ecosystem audit + render
  descriptor suites: **passed** (gbif `avoidWhen` wording repaired for the
  T3-14 routing gate in the same campaign).
- Ruff: pass. Pyright: **0 errors, 0 warnings** (2 pre-existing shapely
  stub warnings).
- Disposable runtime hygiene: exact lane persisted, probe passed, owned runtime
  cleaned on stop (`live-runtime.json` status `STOPPED`).

## Remaining boundary

The earthquakes-specific render, valid-empty, attribution, and acknowledgement
boundaries are now proven. Visibility mutation (hide/show) and remove/re-add
use the shared overlay-controls lifecycle already validated for the same USGS
provider family in T3-02 and for overlay removal in T3-06; no
earthquakes-specific defect was observed in that mechanism.