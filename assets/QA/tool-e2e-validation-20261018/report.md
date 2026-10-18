# Tool interaction and end-to-end validation

Last updated: 2026-10-18

## Tested boundary

- Branch `develop`, base `c93996ea`, plus the source changes fingerprinted in [slice.json](slice.json).
- `app/server/.venv`, production Angular build served by an isolated backend on `127.0.0.1:5079`.
- Disposable data root (a copy of the canonical database under `runtimes/cache/test-runtime`), deleted after the run.
- Exact lane `opencode-go / deepseek-v4.1-flash`. The structured probe passed, and no provider or model was substituted.
- In-app browser at 1440×900. Every map result was judged from a screenshot, not only the DOM or the acknowledgement.
- About 32 live agent runs.

## Inventory

All 10 native tools and all 68 executable catalog capabilities are listed in [tool-inventory.md](tool-inventory.md).

- **Credentials.** The copied canonical database holds no geospatial provider credentials, only the `opencode-go` model key. Every credentialed tool (TomTom, OpenAQ, OpenTripMap, FIRMS, OpenChargeMap, Windy) returns an honest `missing-credential` result. T4-07 stays BLOCKED.
- **Gap-only direct checks.** The 37 cases are in [provider-matrix.json](provider-matrix.json):
  - Boundary inputs are rejected with HTTP 400: malformed bbox, inverted bbox, out-of-range bbox, antimeridian-crossing bbox, and bad time.
  - Unknown IDs return 404.
  - Disabled capabilities now return 403.
  - Dataset-ingestion and metadata-only kinds return descriptors only. No upstream data is retrieved for them.

## Defects found and fixed

Each fix has a regression test that failed on the unfixed source and passes after the fix, unless stated otherwise.

| # | Defect, with the run that exposed it | Fix | Test |
|---|---|---|---|
| 1 | The OpenCode adapter treated `deepseek-v4.1-flash` as text-only (name heuristic). A real image probe showed the model reads images, so vision was unusable on the only lane. | Added a verified vision-model list per endpoint and exposed `supports_vision` in catalog metadata. | `test_capabilities.py` |
| 2 | The direct `/layers/{id}/features` and `/geojson` endpoints served disabled, restricted-use sources (Open-Meteo elevation), bypassing the opt-in licence policy. | These endpoints now return 403 for disabled capabilities, before any provider is called. | `test_geospatial_api_contracts.py` |
| 3 | After a provider timeout and empty discovery, the user was told "No supported capability matched" (X-01). | The stop message now names the provider failure. Verified live: "The overpass provider did not respond within its execution deadline, and …". | `test_agent_loop_v2.py` |
| 4 | The composer kept the sent text when Enter followed typing within the same frame, a zoneless change-detection race. The next prompt was merged with the old one (X-02). | Programmatic draft writes now also update the textarea. Verified in the browser with the exact failing sequence. | Browser repro only: TestBed's binding semantics cannot reproduce the race, so the attempted spec was removed. |
| 5 | A route with `operation: "compare"` filtered the catalog down to nothing (X-02). | `compare` now maps to the same primitives as `retrieve`. | `test_agentic_manifest_contract.py` |
| 6 | Two same-capability evidence layers for different places collapsed into one, and `fit_evidence` framed only the first place (X-02). | Layers keep their own extent, and the viewport fits the union. Live: Zurich and Lisbon both rendered, ready. | `test_map_plan_service.py` |
| 7 | One shared word vetoed a capability through `avoidWhen`: "rain radar **imagery**" was blocked by "satellite infrared imagery" (X-07). | An avoid condition now needs the whole phrase. | `test_agentic_manifest_contract.py` |
| 8 | A follow-up target spelled as the resolved label ("Zurich, Switzerland") did not match the known key `zurich`. Execution was then withheld or rejected (X-07). | A shared key-or-label matcher is used for exposure, `location_ref` resolution and goal validation. | `test_tools.py` (×2) |
| 9 | Adding a named provider's layer was routed as provider discovery, which never permits `execute` (X-07). | Such a request is normalized to a data-bearing map route. Live: RainViewer was added and the weather layer kept. | `test_capability_router.py` |
| 10 | A plain subject query ("pharmacies") did not count as a routing variant next to an alias variant, so Overpass was filtered out (X-01). | Plain queries match when the catalog names the subject. Live: Overpass was selected and executed. | `test_agentic_manifest_contract.py` |
| 11 | GIBS WMS 1.3.0 requests sent the 1.1.1 `EXCEPTIONS` MIME type. GIBS painted the error into a 200 PNG, which was acknowledged as rendered "wildfire detections" (X-13). | Changed to `EXCEPTIONS=XML`, so errors are non-image and the proxy rejects them. The fresh tiles now contain fire pixels. | `test_geospatial_api_contracts.py` |
| 12 | The vision capture was never requested. `should_capture` runs before any render observation exists and required one. | A prepared candidate now qualifies, and the browser still captures only a ready render. Live: images were attached under `always` and `final_check`. | `test_vision_policy.py` |

Final local gates on the tested source:

- 1103 backend unit tests pass.
- Ruff is clean.
- Strict Pyright reports 0 errors.
- Karma passes 276/276.
- The production build passes.

## Cross-tool workflow results

Per-run tool sequences, render observations, vision events and answer excerpts are in [workflow-matrix.json](workflow-matrix.json). Screenshots are in [screenshots/](screenshots/).

| ID | Result |
|---|---|
| X-01 place → POIs | Routing fixed. Live retrieval is BLOCKED: Overpass upstream returned 502 "at capacity" and took 31 s against the 20 s timeout. The failure message is now accurate. |
| X-02 compare two cities | PASS after fixes 4–6. Every number matches the stored evidence. |
| X-06 follow-up on evidence | PASS. Zero tool calls. The peak gusts match the hourly evidence exactly. |
| X-07 add a layer to the existing map | PASS after fixes 7–9. The radar was added and the weather layer retained, at revision 2. |
| X-08 ambiguity | PASS. "Northern France" produced a clarification, though the candidates offered were poor. |
| X-10 multi-turn context | PASS across turns, including after a reload (history hydration restored the map). |
| X-13 hazard composite | USGS (74 events), NOAA (honest valid-empty), and MODIS as the keyless fire source. The first run was a false pass on error tiles (fix 11). The post-fix evidence is at proxy level, because the browser acknowledgement reused a cached pre-fix tile. |
| X-14 cancellation | PASS. The run went to `cancelled`, with no late tool events. Cancellation inside a parallel batch is still verified only at unit level. |
| X-09 provider failure | Covered by X-01: an honest, attributed failure that did not exhaust the budget. EEA remains BLOCKED upstream. |
| X-11 empty / large results | Empty results are covered by X-13 (NOAA) and the Japan run. A large-result boundary was not run separately. |
| X-12 credential change | BLOCKED. No geospatial credentials are configured. |

## T3-18 and vision

- **T3-18.** All five reconstructed scenarios were observed live:
  - The overlay panel shows `2 of 2 visible`.
  - Valid-empty results are reported honestly.
  - An unsupported request (live trains) is refused and the last-known-good map is preserved.
  - Provenance answers match the stored evidence, without a re-fetch.
  - A valid-empty result is not rendered as an overlay.
- **VISION.**
  - The Settings control is enabled for the lane (VISION-009).
  - `always`: a capture is requested, posted and attached, and the model's description matches the rendered radar (VISION-007 and VISION-008).
  - `final_check`: the image is attached on the terminal call only.
  - `disabled`: no capture.
  - Not run live: `on_failure`, which needs a reproducible render failure, and the capture-failure degradation path (VISION-010).

## Open findings, not fixed

| ID | Finding | Why not fixed |
|---|---|---|
| F-12 | Resolved in the [F-12/vision follow-up](../validation-20261018-f12-vision/report.md): a state-level candidate satisfies a city target only by its own ISO 3166-2 single-city-subdivision code, and its extent is clamped to the city scale. Tokyo resolves; New York still resolves to the city. | — |
| F-13 | When a radar request is framed as a point scope, every bbox/viewport raster is excluded. The model then claimed RainViewer "is not available". | The contract filtering is correct. The real problems are model framing and over-confident narration. |
| F-14 | The pixel-count render check cannot tell an error image from data, and a pre-fix error tile was reused from the browser HTTP cache (`max-age=60`). | Fix 11 removes the known source. A generic content check is a design change. |
| F-15 | WMS requests on the generic manifest path still default to 1.1.1 with `se_inimage`. That pairing is valid, but errors would also render as images. | Changing it was out of scope; no failure was observed. |
| F-16 | A single-point evidence layer fits a street-level viewport of about 250 m. | Pre-existing behaviour, accepted in T3-13. |
| F-17 | Unsupported-request narration says "no registered provider" for a GTFS source that is registered but unconfigured, and leaks process text ("Let me confirm…"). | Model narration. |
| F-18 | The two-city map header names only the first place. | Minor UX. |

## Hosted CI

Not run. Nothing was pushed.
