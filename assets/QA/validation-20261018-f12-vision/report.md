# F-12, credentialed providers and vision leftovers

Last updated: 2026-10-18

## Tested boundary

- Branch `develop`, base `d033d726`, plus the source changes fingerprinted in [slice.json](slice.json).
- `app/server/.venv`. The production Angular build was rebuilt from the current client source ([client-build.log](client-build.log)) and served by an isolated backend on `127.0.0.1:5079`.
- Disposable data root: a SQLite backup of `data/database.db` (integrity `ok`), deleted after the run. The backend was given `UI_PORT=5079` so the realtime origin check matches the single-port harness.
- Exact lane `opencode-go / deepseek-v4.1-flash`. The [structured probe](structured-probe.json) passed. No provider or model was substituted.
- Playwright browser at 1440×900. Every map result was judged from a screenshot, not only from the DOM or the acknowledgement.
- 23 live agent runs, summarised in [run-evidence.json](run-evidence.json). Secrets are not recorded; the evidence files were checked for key material.

## Selected scope

- **F-12** (Tokyo as a city), carried over as uncommitted work in progress, and the T3-18 Tokyo variants it blocked.
- **T4-07 / X-12.** The canonical database gained TomTom, OpenAQ, NASA FIRMS, Windy and OpenChargeMap keys at 15:04–15:06 today, so the gate was no longer blocked by missing configuration.
- **VISION-INSPECT.** `on_failure` and capture-failure degradation (VISION-010) had not been run live.

## Defects found and fixed

Each fix has a regression test that fails on the unfixed source and passes after the fix.

| # | Defect, with the run that exposed it | Fix | Test |
|---|---|---|---|
| 1 | F-12: Nominatim returns Tokyo only as `boundary/administrative`, `addresstype=province`, with no city key. A city target therefore rejected it ("could not safely resolve Tokyo"). | A state-level candidate satisfies a city target only by its own `namedetails.ISO3166-2` code, from a short allow-list of single-city subdivisions (JP-13, DE-BE, DE-HH, RU-MOW, …). The live payloads were probed: New York state (`US-NY`) and São Paulo state (`BR-SP`) carry their own codes and stay rejected. `address.ISO3166-2-lvl4` names the parent and is deliberately not used. | `test_location_resolver_accepts_city_subdivision_only_by_iso_code` |
| 2 | With F-12 accepted, "earthquakes near Tokyo" queried the whole Tokyo Metropolis bbox `[135.85, 20.21, 154.21, 35.90]`, which reaches the Ogasawara Islands and Minami-Torishima. "Near" requests without a distance use the place extent by design (`native_tools._lower_execution_extent`). | A bbox accepted through the city-subdivision path is clamped to ±0.75° around the geocoded centre. Live Tokyo query bbox: `[139.01, 34.93, 140.51, 35.90]`. | same test (bbox assertion) |
| 3 | Windy Webcams never returned live data. The adapter sent `bbox=west,south,east,north`, but API v3 expects `north,east,south,west`. The wrong order got an HTTP 500; the correct order returns 1,125 cameras. | Corrected the bbox order. | `test_windy_webcam_provider_builds_bbox_camera_request` and the adapter-core test |
| 4 | The Windy camera-type filter was silently ignored: v3 accepts `categories`, not `category`. `traffic` returned all 1,125 cameras instead of 11. | Use `categories`. | same test |
| 5 | A descriptor-only (non-live) Windy call was cached as "last response". A later live failure was then reported as `stale` camera metadata with 0 features, which hid the real error. | Descriptor responses are no longer cached. | `test_windy_webcam_live_failure_after_descriptor_is_not_reported_stale` |
| 6 | `capture_missing` was traced on every terminal call that had a ready render, including `disabled` policy and failure-free `on_failure` runs. A real capture failure (VISION-010) could not be told apart from "no image wanted". | The policy is judged as if the capture existed, so `capture_missing` is recorded only when an image was wanted but never arrived. | `test_capture_missing_is_traced_only_when_an_image_was_wanted` |
| 7 | European rain-radar requests (Germany, Brest) ended with "Capability is outside its declared geographic coverage". The model described RainViewer (success) and NOAA radar (CONUS-only) in one batch, and the NOAA coverage `policy_rejection` with `request_user_input` stopped the whole run. | A coverage rejection asks the user only when nothing else in the same batch succeeded. Other `request_user_input` outcomes are unchanged. Live: Germany and Brest now render RainViewer, and FEMA-in-Zurich still stops at the coverage guardrail. | `test_coverage_rejection_stops_only_without_an_in_coverage_alternative` |

Final local gates on the tested source:

- 1,110 backend unit tests pass ([log](backend-unit-full.log)).
- Ruff is clean ([log](ruff.log)).
- Strict Pyright reports 0 errors, 0 warnings, 0 informations ([log](pyright.log)).
- No client source changed. The production build passes, and Karma was not re-run.

## Results

### F-12 and T3-18 Tokyo variants

| Run | Result |
|---|---|
| "Show me Tokyo on the map" | PASS. Resolved `Tokyo, Japan` as a city, centred at 139.764°E, 35.677°N, render `ready` ([screenshot](screenshots/f12-tokyo-city.jpg)). |
| "Show me New York on the map" | PASS. Resolved the city (centre 40.713°N, 74.006°W, NYC viewport), never the state ([screenshot](screenshots/f12-ny.jpg)). |
| T3-18: "Show recent earthquakes around Tokyo on the map and describe what the rendered map shows" | PASS. Tokyo resolved, the query bbox was clamped, and the USGS result was honest valid-empty with no overlay rendered and the map preserved. USGS `all_hour` and `all_day` confirm 0 events in that bbox ([screenshot](screenshots/t3-18-tokyo-earthquakes.jpg)). |
| T3-18: "Add live subway train positions for Tokyo to this map" on a rendered Tokyo map | PASS. Refused ("No supported capability matched…"), with the Tokyo map preserved ([screenshot](screenshots/t3-18-tokyo-unsupported.jpg)). |
| "Show earthquakes near Tokyo from the past week" | Not a resolver issue (Tokyo resolved). USGS declares `temporal_modes: ["current"]` with only a `recent_feed` window, so an explicit one-week range is filtered out at discovery (new finding F-19). |

### T4-07 credentialed providers

Direct live retrieval with the configured keys is in [credentialed-provider-matrix.json](credentialed-provider-matrix.json); it uses `live=true`, and requests without it return descriptors only:

| Capability | Live retrieval | Agent end-to-end (browser) |
|---|---|---|
| `tomtom_traffic_incidents` | 130 features, TomTom attribution | **FAIL.** 300 incidents retrieved for Rome, but `spatial_scope_satisfied=false` against the administrative geometry. Renders were reported failed although sources and layers loaded (F-21). |
| `tomtom_traffic_flow` | Raster tile descriptor | **FAIL.** The descriptor is typed `unknown`/not renderable, and the run reached the execution limit (F-22). |
| `openaq_air_quality` | 10 stations | **FAIL.** The manifest declares `render_support: "metadata_only"`, so discovery drops it for every map request, which contradicts `supports_map: true` in the runtime profile (F-23). |
| `nasa_firms_active_fires` | 22 detections | **PASS.** 81 California detections rendered and verified ([screenshot](screenshots/t4-07-firms.jpg)). "Northern California" itself is not resolvable as a place. |
| `openchargemap_ev_charging` | 100 stations | **PASS.** Clustered points rendered with Open Charge Map attribution ([screenshot](screenshots/t4-07-ocm.jpg)). |
| `windy_webcams` | 50 cameras (after fixes 3–5) | **PASS.** 8 Lucerne webcams rendered and verified ([screenshot](screenshots/t4-07-windy.jpg)). |
| `opentripmap_tourism_pois` | `auth_required` | BLOCKED. No OpenTripMap key is configured. |

X-12 (credential change): credential presence now turns `missing-credential` results into live data for six providers. An in-session add, rotate or remove of a credential was not exercised.

### VISION-INSPECT

| Case | Result |
|---|---|
| `on_failure` positive (natural failure, no injection) | PASS. Rouen radar: the first `apply_map_plan` failed (`viewport_bounds_unavailable`) and armed the policy. The next prepared candidate requested a capture, which was attached on the terminal call (`vision_calls=1`). |
| `on_failure` negative | PASS. Lisbon (location only) and Rome EV charging (data layer) had no failed tool results: no capture was requested and nothing was attached. |
| Capture-failure degradation (VISION-010) | PASS under a controlled fault. Under `always`, Playwright aborted the `POST /api/geospatial/render-captures` call. The client logged "Map capture for vision inspection failed; continuing without it", the backend traced `capture_missing`, there were no failed tools or retries, and the run completed with presentation `ready` ([screenshot](screenshots/vision-010-capture-post-aborted.jpg)). The fault was injected in the browser; provider and lane were live. |
| `always` non-regression after fix 6 | PASS. Germany and Brest attached their captures. The Brest description matches the rendered radar: Brest dry, the heavy band between Guernsey/Jersey and Normandy, and showers near Rennes, Nantes and Angers ([screenshot](screenshots/coverage-brest.jpg)). |

## Open findings, not fixed

| ID | Finding | Why not fixed |
|---|---|---|
| F-19 | USGS earthquakes cannot serve an explicit time range ("past week") even though the provider publishes `all_week`/`all_month` feeds. The contract declares only `current`. | This is an execution-contract and adapter extension, not a defect in the validated scope. |
| F-21 | TomTom incidents fails `spatial_scope_applied` for an administrative scope, and its render is reported `failed` with all checks true. | This needs agent/render-contract work; it is part of the proposed credentialed-provider follow-up. |
| F-22 | The TomTom flow raster descriptor is not admitted as renderable evidence. | Same follow-up. |
| F-23 | The OpenAQ manifest `render_support: metadata_only` contradicts its runtime profile and its point payload. | Changing it needs the render path validated; same follow-up. |
| F-24 | After a recovered coverage rejection, the status bar still shows "Tool activity: Needs attention" on a completed run. | Minor UX. |

F-13 to F-18 from the [2026-10-18 report](../tool-e2e-validation-20261018/report.md) are unchanged.

## Runtime cleanup

The backend task and browser were stopped, and port `5079` was confirmed free. The disposable data root, backend log and pytest temp folders were deleted. This session's Playwright snapshots were removed from the gitignored `.playwright-mcp/`; the browser console log is kept as [browser-console.log](browser-console.log).
