# Tier 3 route-matrix continuation — ISSUE-006 / ROUTE-LIVE rows + EEA raster render retry

Date: 2026-10-01
Branch: `validation`
Validated source: current working tree (`HEAD` + one in-scope EEA proxy fix in
`app/server/services/geospatial/raster_tiles.py` + tests)
Runtime: disposable exact-lane backend (`scripts/validation/run_t3_07_live_runtime.py`),
isolated data root under `runtimes/cache/test-runtime/`, backend
`http://127.0.0.1:5079`, exact `opencode-go / deepseek-v4.1-flash` lane persisted
through the Settings API and verified by the native structured probe
(`provider=opencode-go`, `model=deepseek-v4.1-flash`, `parse_status=complete`).
Evidence harness: `app/tests/e2e/test_route_matrix_live.py` (browser-authoritative;
the persisted UI outcome is the acceptance authority).

## Scope

Runs the defined Tier 3 / `ROUTE-LIVE` natural-language rows from `ISSUE-006`
(Census demographics, Open-Meteo aliases, Acropolis semantics, imagery extent,
weather budget, generic-infrastructure clarification) and the EEA public-raster
render retry (`RASTER-LIVE` / `GEO-FOCUS-16` `PARTIAL`). Each scenario captures
the run trace (route, selected capabilities, model/tool call counts, terminal
reason, render preparation), browser map state, attribution, and network
evidence (AEGIS proxy vs direct-upstream). Both a pre-fix and a post-fix run were
recorded; the pre-fix evidence is archived under `pre-fix/`.

## Results (post-fix run; `reports/ROUTE-MATRIX-LIVE.json`)

| Scenario | Prompt | Result | Evidence summary |
| --- | --- | --- | --- |
| `acropolis_athens` | Show me the Acropolis. | **PASS** | Location resolved to Acropolis, Athens, Greece (23.7263°E, 37.9717°N); OSM basemap rendered; "Render status: Verified ready"; 24 same-origin proxy tiles; accepted render. Run `run_7b4449aad1bd45b39d014290f48e8bf5`. |
| `openmeteo_alias_milan_air` | How is the air quality in Milan right now? | **PASS** | Routed to `get_air_quality_forecast`; returned PM10 ~27.5, PM2.5 ~20.7, NO2 ~22.1, O3 ~78 µg/m³, "Moderate". No map. |
| `openmeteo_alias_oslo_weather` | Is it cold in Oslo right now? | **PASS** | Routed to `get_weather_forecast`; returned 16.9°C, 0.0 mm, humidity 68%, wind 10.8 km/h, "partly cloudy". No map. |
| `generic_infrastructure_rome` | Show infrastructure in Rome. | **PASS** | Router emitted `ambiguous_infrastructure_category` clarification; 0 provider executions; no map. |
| `census_demographics_chicago` | Show census tracts around Chicago, Illinois. | **PARTIAL** | Route reached manual-toggle census capabilities (`census_cartographic_boundaries` dataset-ingestion and `census_tigerweb_demographics`, both `agenticUse.defaultEnabled:false`); `execute_geospatial_capability:failed`; discovery returned `valid_empty`; run ended "No supported capability matched the request after discovery", no map/data. Census demographics remain not agent-reachable without manual enablement. |
| `openmeteo_alias_elevation` | What is the elevation of Rome, Italy? | **PARTIAL** | Routed to `retrieve_elevation` but the exact lane selected NASA GIBS `SRTM_Color_Index` raster overlay, not the numeric `openmeteo_elevation` point-insight (which is `defaultEnabled:false`). The assistant narrated the limitation ("raster terrain-relief overlay, not a numeric elevation value"). Elevation alias row remains open. |
| `imagery_extent_rome` | Show current satellite context for Rome, Italy. | **PARTIAL** | Map plan for `esri_world_imagery` + `VIIRS_SNPP_CorrectedReflectance_TrueColor` failed backend render validation (`render_validation_failed`: `temporal_scope_applied`, `spatial_scope_applied` not satisfied); post-fix run also recorded the model calling non-exposed tool names (`discover_capabilities`, `execute_capability`). No map rendered. |
| `weather_budget_denver` | What will the weather be in Denver, Colorado tomorrow? | **FAIL (reproducible)** | Both pre- and post-fix runs ended with "The agent reached its configured execution limit." after the 4-call budget (location resolved, capability executed successfully at iteration 3, but no final answer). Weather forecast with a day-ahead temporal scope exhausts the runtime execution budget. This is the `ISSUE-006` "weather budget" row. |
| `eea_noise_milan` | Show noise exposure in Milan. | **PARTIAL** | Provider retrieval passes (attributed EEA WMS raster descriptor, spatial scope satisfied). Post-fix the browser no longer makes direct upstream requests: `direct_upstream_browser_request_count=0`, EEA now loads through `/api/geospatial/tiles/eea_noise_2019/{z}/{x}/{y}.png`. The proxy returns clean `502 application/json` because the configured upstream `https://noise.discomap.eea.europa.eu/arcgis/services/noiseStoryMap/noise_exposure_2019/MapServer/WMSServer` is **retired (HTTP 404 from EEA's own server)**. External upstream boundary. |

## Fix applied (in scope)

`app/server/services/geospatial/raster_tiles.py` — `_BACKEND_RASTER_PROVIDERS`
now includes `eea`, so the EEA WMS browser descriptor is routed through the
manifest-backed AEGIS tile proxy (same-origin) like ESA, FEMA, GIBS, and
RainViewer. This is the established remediation for public raster providers whose
direct cross-origin sources fail at the MapLibre load boundary (pre-fix: 24
browser `ERR_FAILED`/`ERR_ABORTED` requests direct to `noise.discomap.eea.europa.eu`;
post-fix: 0 direct requests, clean proxy 502 with backend diagnostics).

Tests added/updated:
- `app/tests/unit/services/geospatial/test_render_descriptors.py` —
  `test_catalog_public_raster_descriptors_use_backend_proxy` now parametrizes
  `eea_noise_2019` → `noise.discomap.eea.europa.eu` (WMS) and asserts the proxy
  `tile_url_template`.
- `app/tests/unit/test_geospatial_api_contracts.py` —
  `test_geospatial_eea_tile_proxy_materializes_bounded_wms_get_map_request`
  asserts the tile route materializes the EEA WMS GetMap (layers `0`, WMS 1.1.1,
  `srs=EPSG:3857`) and fetches it server-side.

## Quality gates

- Focused geospatial/agent/ingestion regression suite: **231 passed**.
- Affected render-descriptor + API-contract suites: **84 passed** (includes the
  new EEA cases).
- Strict production layer auditor: **86 manifests, `error_count=0`,
  `warning_count=0`, `issues=[]`**.
- Ruff: **pass** on all changed files and the repository.
- Pyright (full repo, `app/server/pyproject.toml`): **0 errors, 0 warnings,
  0 informations**.

## Boundaries and remaining status

- `eea_noise_milan`: provider retrieval and proxy transport now pass; the render
  is **blocked by upstream retirement** (`noise.discomap.eea.europa.eu` 2019 WMS
  returns 404 from EEA's own server; EEA moved to `noise.eea.europa.eu` /
  `portal.discomap.eea.europa.eu` with END-2022 services). The repository's own
  ecosystem audit already classifies this as `eea-noise-upstream-service` /
  `upstream_unavailable` (high). Re-pointing the manifest to the current EEA
  noise service is a data-maintenance/product decision, recorded as follow-up.
- `weather_budget_denver`: reproducible budget exhaustion; the root cause is the
  model/tool-call sequencing in the exact lane (repeated `describe` calls plus a
  day-ahead temporal scope), not a deterministic repository contract. Kept open.
- `census_demographics_chicago`, `openmeteo_alias_elevation`,
  `imagery_extent_rome`: remain `PARTIAL` (manual-toggle / model-behavior /
  render-scope boundaries) with the evidence above. No speculative code change
  was made.
- `T3-10`–`T3-18` remain `UNRUN`: their acceptance criteria are not preserved in
  the repository or its history and must be established before execution.
- FEMA composition (GEO-HYD-05/06), credentialed sources, and provider parity
  were not re-validated here; the last T3-07 run validated only FEMA and ESA
  standalone renders, so those boundaries remain open as documented.

## Cleanup

The disposable exact-lane backend was stopped via the STOP marker and the owned
runtime cleaned; port `5079` is free. No runtime database, user data, or
credentials were modified; the opencode-go credential was resolved in-process
and never recorded.