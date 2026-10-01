# T3-12 — Overpass residential buildings and POI amenity overlays

Date: 2026-10-01
Branch: `validation` (working tree)
Validated source: current working tree (provider circle-coverage spatial scope)
Runtime: isolated `runtimes/cache/test-runtime/t3-07-live-*`; exact
`opencode-go / deepseek-v4.1-flash` lane persisted through the Settings API and
verified by the native structured probe.
Evidence package: `T3-12/` under this directory.

## Result

All three T3-12 scenarios pass the browser-authoritative acceptance boundary.
Residential building footprints render as polygons, POI amenities render as
clustered points, and a bounded desert query returns an honest no-results
outcome — all with `© OpenStreetMap contributors (ODbL)` attribution and an
accepted `map.render_ack`, and zero direct-upstream browser requests.

| Scenario | Classification | Overlay status | Attribution | Render ack | Direct upstream |
| --- | --- | --- | --- | --- | ---: |
| `t3_12_buildings_rome` | `map_render_pass` | `loaded` (510 footprints) | "© OpenStreetMap contributors (ODbL)" | `render_observed` (ready) | 0 |
| `t3_12_poi_bologna` | `map_render_pass` | `loaded` | "© OpenStreetMap contributors (ODbL)" | `render_observed` (ready) | 0 |
| `t3_12_poi_valid_empty` | `map_render_pass` | valid-empty | — | `render_observed` (ready) | 0 |

Screenshots, per-scenario network evidence, and run traces are in `screenshots/`,
`http/`, and `reports/`.

## Root cause found and surgical fix

The first buildings run reached provider execution and rendered 510 building
footprints in the browser, but the ack was rejected at backend validation on
`spatial_scope_applied`. The bbox spatial-scope intersection check used the
resolved location's geocoder bbox (the small Colosseum POI extent), while the
Overpass `around` query legitimately returned a wider radius-bounded
neighborhood. The Overpass adapter already declares the authoritative scope on
its response (`coverage = {type: circle, center, radius_m}`); `capability_execution`
now honors a provider-declared circle as the spatial scope instead of applying
the narrow bbox check. One transient Overpass provider timeout was observed on
a valid-empty re-attempt and recovered on retry; it was not a repository defect.

## Quality gates

- Backend focused suites: **401 passed** (agent + geospatial unit suites
  including the new circle-coverage spatial-scope test).
- Ruff: pass. Pyright: **0 errors**.
- Disposable runtime hygiene: exact lane persisted, probe passed, owned runtime
  cleaned on stop.

## Remaining boundary

The buildings/POI render, attribution, valid-empty, and acknowledgement
boundaries are now proven. Visibility mutation and remove/re-add use the shared
overlay-controls lifecycle validated in T3-02/T3-06. Overpass's documented
partial general reliability remains a provider-level property.