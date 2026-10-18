# Credentialed-provider follow-up: F-21, F-22, F-23

Last updated: 2026-10-18

## Tested boundary

- Branch `develop`, base `815fb89d`, plus the source changes fingerprinted in [slice.json](slice.json).
- `app/server/.venv`. The production Angular build in `app/client/dist` (built 18:16 today, after the last client source change) was served by an isolated backend on `127.0.0.1:5079`. No client source changed.
- Disposable data root: a SQLite backup of `data/database.db` (integrity `ok`), deleted after the run. The backend ran with `UI_PORT=5079` so the realtime origin check matches the single-port harness.
- Exact lane `opencode-go / deepseek-v4.1-flash`. The native tool probe passed in Settings before the runs. No provider or model was substituted.
- Playwright browser at 1440×900. Each map was judged from a screenshot, not only from the DOM or the acknowledgement.
- Secrets are not recorded. The evidence files were checked for key material.

## Defects found and fixed

Each fix has a regression test that fails on the unfixed source and passes after the fix.

| # | Defect, with the evidence that exposed it | Fix | Test |
|---|---|---|---|
| F-23a | The OpenAQ manifest declared `render_support: "metadata_only"`, so discovery with `requires_render` dropped it for every map request, although the runtime profile says `supports_map: true` and the provider returns point features. | `render_support: "vector"`. The provider already returns `result_type="features"` with latitude/longitude points, the same shape Open Charge Map renders. | `test_openaq_stations_are_discoverable_for_a_map_request` |
| F-23b | With F-23a alone, the live run still failed: the model searched "air quality monitoring stations" and "air quality sensors". Once `air quality` is mapped to an alias, every remaining word must occur in the manifest, and OpenAQ's description ("air-quality locations") contained none of `monitoring`, `stations`, `sensors`. | The description now says what the source serves: "air-quality monitoring stations and sensors". | Same test, which uses the two live queries. It fails with either half of F-23 missing. |
| F-21 | "Show current traffic incidents in Rome on the map": TomTom returns every incident line that intersects the bbox, and the adapter took each line's first vertex as its point. A live Rome query had 3 of 281 points outside the bbox, so the all-features intersection check set `spatial_scope_satisfied=false`. The render "failure" with all browser checks true came from that: the server rejected the ready acknowledgement because `spatial_scope_applied` was still pending. | When a bbox was queried, the point is the first vertex inside it. Otherwise it is a representative point of the part of the line inside the bbox. The response is also typed `result_type="features"`. Live: 0 of 277 points outside. | `test_tomtom_incident_point_lies_inside_the_requested_bbox` |
| F-22a | "Show live traffic flow in Rome on the map": the flow response carried a same-origin `tileUrl` but no `result_type`, so it defaulted to `unknown`, `map_eligibility` was `unknown`, and `apply_map_plan` rejected it as `evidence_not_renderable`. | The flow response is typed `result_type="raster"`, like RainViewer and GIBS. | `test_tomtom_flow_descriptor_is_renderable_raster_evidence` |
| F-22b | With F-22a alone, the same-origin tile proxy returned HTTP 502 for every tile: it requested `.../tile/flow/absolute/relative0/{z}/{x}/{y}.png`, which has two style segments. TomTom's raster flow path takes exactly one style. | The proxy requests `.../tile/flow/absolute/{z}/{x}/{y}.png`, the style the manifest's own `url_template` declares. Live: tile 12/2190/1520 returns a 29 KB PNG. | Same test (URL assertion). |

Final local gates on the tested source:

- 1,113 backend unit tests pass ([log](backend-unit-full.log)).
- Ruff is clean ([log](ruff.log)).
- Strict Pyright reports 0 errors, 0 warnings, 0 informations ([log](pyright.log)).

## Results

Run details are in [run-evidence.json](run-evidence.json).

| Prompt | Result |
|---|---|
| "Show air quality monitoring stations in Rome on the map" | **PASS.** OpenAQ was discovered, described and executed (10 stations, `spatial_scope_satisfied=true`). The plan applied first time, `map.render_ack` was `ready` on attempt 1 and accepted, and the run completed with presentation `ready`. The screenshot shows station points across Rome, with the OpenAQ layer and attribution, and the answer lists the stations ([screenshot](screenshots/f23-openaq-rome.jpg)). |
| "Show current traffic incidents in Rome on the map" | **PASS.** 267 incidents, `spatial_scope_satisfied=true`. The ready acknowledgement was accepted on attempt 1, and the run completed with presentation `ready`. The screenshot shows clustered incident points over the Rome area with TomTom attribution ([screenshot](screenshots/f21-tomtom-incidents-rome.jpg)). |
| "Show live traffic flow in Rome on the map" | **PASS.** The flow result is `raster` and `renderable`. The model's first plan (fit to the evidence) failed with `viewport_bounds_unavailable`, and it recovered by fitting the resolved location, as the Rouen run did in the previous campaign. The ready acknowledgement was accepted on attempt 1. The screenshot shows TomTom congestion colouring over the road network (green ring roads, orange and red in the centre) ([screenshot](screenshots/f22-tomtom-flow-rome.jpg)). The browser loaded 32 tiles, all from `/api/geospatial/proxy/tomtom/`. It made no request to `api.tomtom.com`, and no URL carried a key. |

T4-07 stays `PARTIAL`, because OpenTripMap still has no key. Every configured credentialed provider (TomTom incidents and flow, OpenAQ, NASA FIRMS, Open Charge Map, Windy) now passes end-to-end.

## Open findings, not fixed

| ID | Finding | Why not fixed |
|---|---|---|
| F-25 | `openmeteo_elevation` has the same contradiction F-23 had: its runtime profile says `supports_map: true`, but its contract is `metadata_only`. It is disabled by default (`restricted_usage_opt_in`). | It is outside this scope, and its render path was not validated. |
| F-24 | After a recovered tool failure, the status bar still shows "Tool activity: Needs attention" on a completed run. It was seen again on the flow run. | Minor UX, carried over. |

F-19 is unchanged.

## Runtime cleanup

The backend and the Playwright browser were stopped, and port `5079` was confirmed free. The disposable data root and the backend log were deleted. The browser console log is kept as [browser-console.log](browser-console.log). Its only errors are WebSocket refusals from a deliberate backend restart while the first, pre-fix conversation was still open.
