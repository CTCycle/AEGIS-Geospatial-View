# Tier 2 Direct Tools, History, and Evidence Inspection

Date: 2026-09-25
Branch: `develop`
Starting commit: `a71230176892020f2802fd63f365196b2bbfaa9d`
Tested boundary: starting commit plus the scoped working-tree changes listed below.
Browser lane: `opencode-go` / `deepseek-v4.1-flash`; Settings showed the model selected and the native tool probe passed.
Runtime: Windows launcher, isolated `AEGIS_DATA_DIR=runtimes/cache/test-runtime/validation-20260924-exact-lane`. UI port 4516 was occupied by task-owned PID 11940, so the launcher failed closed there and the patched validation app ran on verified-free port 4517. No occupied process was terminated.

## Scope and final status

| Slice | Status | Current evidence | Remaining limitation |
| --- | --- | --- | --- |
| `T2-05` Direct tools | `PASS` | Exact-lane browser runs returned Colosseum coordinates without a map; 24 hourly local weather rows; 24 hourly local air-quality rows; and ten pharmacy-only Overpass results with names, categories, and distances. Fresh POI evidence `evidence_7b9168d435714266b547b758a032cb56`, retrieved `2026-09-25T08:21:53.741830+00:00`, contains ten pharmacy records and is not truncated. | One air-quality run rejected model-generated arguments on iteration 3, then succeeded on iteration 4 and completed with all 24 rows. The UI retained a “Needs attention” tool-activity label. Forecasts are provider outputs, not guaranteed observations; Overpass advertises partial general reliability and the request is capped at ten. |
| `T2-06` Conversation history | `PASS` | After restarting the backend on the same isolated data root, a new UI tab hydrated saved history. Reopening the saved map conversation restored its transcript and the Colosseum map. The saved map run `run_ec08c4426cd04adeb706dbf072d84873` completed its render handoff. | This covers saved-history hydration and the observed render replay path, not interrupted-generation, browser-crash, or every concurrent-tab race. |
| `T2-07` Evidence inspection | `PASS` | `run_956625096e234c1aad0752ac6a67e954` completed in one successful `inspect_evidence` call against the immediately preceding POI result. It returned evidence ID, source, retrieval time, count 10, and all ten pharmacy categories without a provider fetch or map render. | The inspection route is conversation-scoped; a fresh conversation without saved evidence does not receive this route. The router test covers that boundary. |

These passes apply to the tested scenarios above. They do not promote the broader live route matrix, capability inventory, raster providers, or provider parity.

## Browser and provider results

Settings verified the selected provider/model lane as `opencode-go` / `deepseek-v4.1-flash`; **Test selected model** returned **Verified / Native tool probe passed**.

- Coordinate lookup returned latitude `41.8909421`, longitude `12.491903`, resolved as the Colosseum in Rome, with an empty map workspace. Earlier live run: `run_8e740f041aaf46efb828faaaeb21afb7`.
- Weather retrieval returned 24 hourly Europe/Rome rows from 2026-09-25 11:00 through 2026-09-26 10:00 local, temperature, precipitation, and wind speed units, with no map.
- Air-quality retrieval returned 24 hourly Europe/Rome rows over the same window for PM2.5, PM10, NO₂, and O₃ in µg/m³, with no map. Run `run_2cab1c8bd5184ebb80d8c64c9e94697e` completed after one rejected tool-argument attempt.
- The fresh Overpass query used `overpass_poi_amenities`, a pharmacy-only category filter, a 2 km radius centered at `41.8909421,12.491903`, and a limit of 10. The initial answer listed all ten names, categories, and distances. The later saved-evidence inspection confirmed status `ok`, not stale, not truncated, all categories `pharmacy`, and `© OpenStreetMap contributors (ODbL)` attribution.
- Historical evidence `evidence_343aa7118f1b4e3ab005bd4221b75e01` contains mixed categories and is not treated as evidence that the current filtered query is clean. The fresh result above is the current evidence.
- Reopening the saved map conversation showed the Colosseum map and OSM attribution. Its map run used saved evidence and did not call Overpass again; the trace records `map_prepared`, `run_suspended`, two `render_observed` events, `run_resumed`, and completion.

## Automated checks

- Focused pytest: **115 passed** across `test_agent_loop_v2.py`, `test_capability_execution.py`, `test_capability_router.py`, `test_direct_service_provenance.py`, and `test_geospatial_provider_adapters_core.py`.
- Ruff: **All checks passed** for the 13 changed Python source and test files.
- `git diff --check`: passed.

The report records the boundary before validation changes were committed. Hosted CI for the eventual commit is a separate exact-head gate and is not claimed here.

## Scoped implementation changes

- Preserve bounded, allowlisted preview rows from feature results in model-visible tool observations so direct text answers can use retrieved records without exposing provider payloads wholesale.
- Keep weather and air-quality hourly windows bounded to 24 local hours and expose allowlisted measurements.
- Normalize direct coordinate and saved-evidence inspection routes so they do not inherit unrelated provider-data requirements; require successful evidence inspection for that task.
- Forward nested category filters through the Overpass adapter and retain hourly forecasts in the Open-Meteo path.

## Overall campaign boundary

After these three Tier 2 slices, the campaign is **22 `PASS`, 2 `PARTIAL`, 0 `BLOCKED`, and 44 `UNRUN` of 68**. Tier 2 is **6 `PASS`, 1 `PARTIAL`, and 0 `UNRUN`**. `T2-04` remains partial at 36/50 discovery candidates and the configured `max_model_calls=4`. `T0-04` remains partial for untested startup outage, ownership-race, and injected-failure cleanup cases. Tier 3–5 and provider-specific parity remain open or blocked as recorded in the canonical ledgers.

## Carried-over incomplete gates

These gates were reviewed against their current ledger evidence. They remain outside the selected `T2-05`/`T2-06`/`T2-07` scope and are not promoted by this validation:

- `T2-04` and `agent.capability-discovery.inventory` remain `PARTIAL`: discovery reached 36 of 50 candidates across three pages and stopped at `max_model_calls=4`. Resume only with an approved budget change or a guard-respecting continuation policy.
- `T0-04` / `runtime.startup.windows-local` remains `PARTIAL`: the launcher override and fresh/warm readiness subset passed, but paired same-machine timing, provider-outage behavior, ownership-change races, and injected startup-failure cleanup remain unverified.
- `ROUTE-LIVE`, `agent.capability-routing.live-language`, `MATRIX-22`, and `testing.complete-live-matrix` remain `PARTIAL`: Acropolis semantics, imagery extent, weather budget, USGS/land-cover aliases, generic-infrastructure clarification, broader multilingual/provider routes, composition, recovery, and Tier 3–5 scenarios remain open.
- `maps.raster-overlays` and `maps.state-preservation` remain `PARTIAL` under `ISSUE-002`: FEMA retrieval did not produce rendered pixels, ESA WorldCover source loading failed, and GIBS was unavailable upstream. Therefore FEMA composition and retention have not been proven, although the saved Colosseum vector-map replay passed.
- `model.provider-parity.openai-ollama` remains `BLOCKED`: the required OpenAI/Ollama services and approved credentials were unavailable for this boundary. No parity or fallback claim is made from the OpenCode Go lane.
- `providers.credentialed-and-local-source-access` remains `BLOCKED`: approved credentials and configured local feeds/snapshots/datasets were unavailable. Their absence is an environment prerequisite, not a product defect.
- `HOSTED-CI` for this scoped source change is pending after publication; the previously recorded hosted result applies to its cited historical commit only. The focused local pytest and Ruff evidence here does not substitute for exact-head CI.

The campaign roll-up's `0 BLOCKED` counts only its 68 Tier 0–5 validation slices; the separate provider-specific component gates above retain their own `BLOCKED` statuses in the project ledger.

## Process cleanup

At closeout, no listener remained on ports 4512–4517 or 7059, and none of the recorded task-owned launcher/backend PIDs remained. No unrelated process was stopped. The isolated validation data root was retained with the user's saved provider configuration.
