# T3-07 / T3-08 implementation and validation

Date: 2026-09-29
Branch: `develop`
Tested source: `develop@411adb4fc0c1` plus the uncommitted working-tree proxy fix
Required live lane: `opencode-go / deepseek-v4.1-flash`

## Result

The application-owned raster transport is implemented and the exact lane was
verified in the isolated runtime. The live browser gates remain deliberately
unpromoted:

- `T3-07`: `PARTIAL` remains correct. FEMA and ESA requests reached the
  same-origin AEGIS proxy with zero direct-upstream browser requests. The
  proxy returned provider-side `502` responses for the public raster tiles;
  no provider image response, MapLibre source/layer state, visible pixels, or
  accepted `map.render_ack` was observed.
- `T3-08`: `UNRUN` remains correct. All 12 parameterized GIBS browser cases
  ran with the exact lane, but each assistant run reached its configured
  execution limit before a raster route was produced. Each case therefore
  recorded zero proxy requests and zero direct-upstream requests.
- Campaign roll-up remains `30 PASS / 1 PARTIAL / 0 BLOCKED / 37 UNRUN`.

The exact-lane preflight passed with HTTP 200, provider `opencode-go`, model
`deepseek-v4.1-flash`, protocol `openai-chat-completions`, and complete parse
status. The model key was entered only into the isolated runtime Settings
flow; it is not present in source, QA, or this report.

## Implemented boundary

- Added deterministic WMS, WMTS, XYZ, coordinate, Web Mercator bbox, and
  unresolved-placeholder handling in `raster_tiles.py`.
- Extended the manifest-backed tile endpoint for FEMA ArcGIS export, ESA
  WorldCover WMTS, and provider-described NASA GIBS WMTS/WMS fallback.
- Centralized the public-raster proxy-template builder and applied it to the
  native `apply_map_plan` descriptor path as well as the render-descriptor
  service. Direct provider URLs remain provenance in `source_url`; MapLibre
  receives the same-origin proxy template.
- Added sanitized provider-classified upstream target logging. Credentials
  and sensitive query values are redacted before logging.
- Kept the frontend renderer generic; its regression verifies that the proxy
  template is passed unchanged to a MapLibre raster source/layer.

## Validation

- Scoped backend regression suites after the proxy fix: `91 passed`, 2
  dependency deprecation warnings.
- Earlier implementation quality gates remain recorded in
  `quality-checks.log`: full backend unit suite, Ruff, Pyright, strict
  manifest audit, frontend build, Karma, and geospatial browser smoke all
  passed on the base implementation boundary.
- Live FEMA/ESA diagnostic: `1 passed`; both scenarios reached proxy transport
  and ended with provider-side render failure (`direct_upstream: 0`).
- GIBS matrix: `12 passed` as test harness executions; all 12 scenario
  classifications were `proxy_route_failure` because the assistant reached
  its execution limit before producing a raster route.
- Direct proxy spot checks: FEMA and ESA returned sanitized JSON `502`
  responses with provider-specific failure details.
- No provider raster success, visible raster pixels, or accepted
  `map.render_ack` is claimed by this package.
- The isolated backend and frontend were stopped after validation; ports
  `7059` and `4512` were clear.

See `slice.json`, `browser-evidence.md`, `network-summary.json`,
`run-summary.json`, `quality-checks.log`, and the per-layer files under
`reports/` for the durable details. Fresh raw rerun artifacts remain under
`assets/QA/tier3-validation-develop-20260929-t3-07-t3-08-rerun/`.
