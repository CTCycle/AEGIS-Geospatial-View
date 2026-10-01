# ROUTE-MATRIX-LIVE browser evidence

Exact-lane `opencode-go / deepseek-v4.1-flash` browser runs against the isolated
runtime (`http://127.0.0.1:5079`). Two full harness runs were recorded: the
pre-fix run (archived under `pre-fix/`) and the post-fix run
(`reports/ROUTE-MATRIX-LIVE.json`, `http/ROUTE-MATRIX-LIVE/`,
`screenshots/ROUTE-MATRIX-LIVE/`). The harness is
`app/tests/e2e/test_route_matrix_live.py`; every scenario records the run trace,
selected capabilities, model/tool call counts, terminal reason, browser map
state, attribution, and AEGIS-proxy vs direct-upstream network events.

## Pass cases

- **Acropolis**: resolved to Acropolis, Athens, Greece (23.7263°E, 37.9717°N);
  OpenStreetMap basemap; "Render status: Verified ready"; 24 same-origin proxy
  tiles; accepted render. Run `run_7b4449aad1bd45b39d014290f48e8bf5` /
  conversation `conv_8433304154c54614b2241c3dc56ffdd1`.
- **Air quality (Milan)**: `get_air_quality_forecast` → PM10 ~27.5, PM2.5 ~20.7,
  NO2 ~22.1, O3 ~78 µg/m³, overall "Moderate".
- **Weather (Oslo)**: `get_weather_forecast` → 16.9°C, 0.0 mm, humidity 68%,
  wind 10.8 km/h, "partly cloudy".
- **Generic infrastructure (Rome)**: `ambiguous_infrastructure_category`
  clarification; 0 provider executions; no map (matches the capability-router
  unit contract `test_router_clarifies_broad_infrastructure_category_before_shortlisting`).

## EEA transport fix (pre- vs post-fix)

| Metric | Pre-fix | Post-fix |
| --- | ---: | ---: |
| Direct upstream browser requests | 24 (`ERR_FAILED`/`ERR_ABORTED` to `noise.discomap.eea.europa.eu`) | **0** |
| AEGIS proxy `eea_noise_2019` requests | 0 | 70 |
| Proxy tile responses | n/a | 502 `application/json` (upstream 404) |

Post-fix, the EEA WMS descriptor is served through
`/api/geospatial/tiles/eea_noise_2019/{z}/{x}/{y}.png`; the browser makes no
cross-origin requests. The remaining render failure is the retired upstream
(`noise.discomap.eea.europa.eu` 2019 WMS returns 404 from EEA's own server),
which the repository ecosystem audit already classifies as
`eea-noise-upstream-service` / `upstream_unavailable`.

## Weather forecast (budget) — PASS at adequate budget

`weather_budget_denver` ("What will the weather be in Denver, Colorado
tomorrow?") at the default `simple_max_model_calls=4` budget ends with "The
agent reached its configured execution limit." — the runtime budget, not a
product failure. With the runtime budget raised to `simple_max_model_calls=10`
(via `/api/settings/runtime`, restart), the same request completes with a full
Open-Meteo forecast: Denver 39.739°N, 104.985°W, ~10→22°C, 0.0 mm, overcast
(WMO 3), 7 model calls. See `budget-run/http/ROUTE-MATRIX-LIVE/weather_budget_denver.json`,
run `run_8c9fad36dbae4c5ea1a662449774172c`.

## Remaining partial rows

- **Census demographics (Chicago)**: route reached manual-toggle census
  capabilities (`defaultEnabled:false`); execution failed; discovery
  `valid_empty`; run ended "No supported capability matched the request after
  discovery"; no map/data.
- **Imagery extent (Rome)**: map plan for `esri_world_imagery` +
  `VIIRS_SNPP_CorrectedReflectance_TrueColor` failed backend render validation
  (`temporal_scope_applied`, `spatial_scope_applied`); no map rendered.
- **Elevation (Rome)**: exact lane selected the SRTM raster overlay, not the
  numeric `openmeteo_elevation` point-insight (which is `defaultEnabled:false`);
  the assistant narrated the limitation.

Screenshots: `screenshots/ROUTE-MATRIX-LIVE/*.png`. Per-scenario network +
trace evidence: `http/ROUTE-MATRIX-LIVE/*.json`.