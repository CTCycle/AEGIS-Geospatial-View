# T3-07 / T3-08 implementation and validation

Date: 2026-09-29
Branch: `develop`
Tested source: `b0be47ccdf40a5288d205607e45e5d9aaa079d5a` plus the uncommitted working-tree changes in this package
Required live lane: `opencode-go / deepseek-v4.1-flash`

## Result

The application-owned raster transport is implemented and its local contracts pass. The live browser gates were not promoted:

- `T3-07`: `PARTIAL` remains correct. The exact-lane preflight returned HTTP 200 but reported empty provider/model values with `status=failed` and `parse_status=failed`; the FEMA/ESA browser scenarios therefore skipped before a provider request.
- `T3-08`: `UNRUN` remains correct. All 12 parameterized GIBS cases reached the same exact-lane preflight boundary and skipped before layer discovery or raster transport.
- Campaign roll-up remains `30 PASS / 1 PARTIAL / 0 BLOCKED / 37 UNRUN`.

No live raster response, HTTP status, screenshot, MapLibre source/layer state, visible raster pixels, or accepted `map.render_ack` is claimed by this package.

## Implemented boundary

- Added deterministic WMS, WMTS, XYZ, coordinate, Web Mercator bbox, and unresolved-placeholder handling in `raster_tiles.py`.
- Extended the manifest-backed tile endpoint for FEMA ArcGIS export, ESA WorldCover WMTS, and provider-described NASA GIBS WMTS/WMS fallback.
- Changed FEMA, ESA, static GIBS, and provider-discovered GIBS browser descriptors to use the same-origin AEGIS tile proxy while retaining provider URL, protocol, attribution, layer, and time metadata.
- Added sanitized provider-classified upstream target logging. Credentials and sensitive query values are redacted before logging.
- Kept the frontend renderer generic; its regression verifies that the proxy template is passed unchanged to a MapLibre raster source/layer.

## Validation

- Focused geospatial backend suites: `71 passed`, 2 dependency deprecation warnings.
- Full backend unit suite: `971 passed`, 2 dependency deprecation warnings.
- Ruff: passed on changed Python files and repository scope with `--no-cache`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- Strict production manifest audit: `86` manifests, `0` errors, `0` warnings.
- Frontend production build: passed.
- Frontend Karma suite: `254 SUCCESS`.
- Geospatial browser-smoke suite: `6 SUCCESS`.
- Live raster diagnostic: `1 skipped` at exact-lane preflight.
- GIBS matrix: `12 skipped` at exact-lane preflight.
- SQLite integrity check on the isolated runtime database: `ok`.
- Ports `7059` and `4512` were clear after service shutdown.

The repository `uv run` wrapper could not use its protected global uv cache in this Windows environment, so the existing `app/server/.venv` was used for the same commands. No provider or model fallback was used.

See `slice.json`, `browser-evidence.md`, `network-summary.json`, `run-summary.json`, `quality-checks.log`, and the per-layer files under `reports/` for the durable details.
