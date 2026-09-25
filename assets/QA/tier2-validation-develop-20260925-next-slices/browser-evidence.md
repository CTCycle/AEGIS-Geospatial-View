# Browser Evidence — 2026-09-25 Tier 2 Slices

Environment: Windows official launcher; isolated `AEGIS_DATA_DIR=runtimes/cache/test-runtime/validation-20260924-exact-lane`; validation UI `http://127.0.0.1:4517/`. Port 4516 was held by task-owned PID 11940, so the launcher failed closed and the test ran on verified-free port 4517. Backend readiness passed on port 7059.

Selected Settings lane: provider `opencode-go`, model `deepseek-v4.1-flash`. **Test selected model** showed **Verified / Native tool probe passed**. No model or provider substitution was used.

## Fresh direct tools (`T2-05`)

### Coordinate lookup

The Colosseum resolved to latitude `41.8909421`, longitude `12.491903`. The answer was text-only and the workspace remained an empty map canvas. Earlier live run identity: `run_8e740f041aaf46efb828faaaeb21afb7`.

### Weather

The browser showed an Open-Meteo point forecast for Europe/Rome with 24 rows from `2026-09-25 11:00` through `2026-09-26 10:00` local time. The table included time, temperature (°C), precipitation (mm), and wind speed (km/h); no map was rendered. The assistant stated the window was not truncated.

### Air quality

The browser showed an Open-Meteo point forecast with 24 local hourly rows over the same window. Columns were PM2.5, PM10, NO₂, and O₃, all in µg/m³. No map was rendered. Execution run `run_2cab1c8bd5184ebb80d8c64c9e94697e` completed: location resolution and two capability descriptions succeeded, one execution call was rejected for semantic argument validation on iteration 3, and the execution succeeded on iteration 4. Required data, temporal scope, spatial scope, and root task completed. The tool-activity label remained “Needs attention”; that recovered failure is recorded as a limitation.

### Pharmacy-only POI query and saved result

The live browser request searched within 2,000 m of the Colosseum, applied the pharmacy category filter, capped the result at ten, and requested text only. The first answer rendered all ten names, categories, and distances; the map workspace stayed empty. It disclosed Overpass’s partial general reliability and did not claim that more pharmacies could not exist beyond the ten-item cap.

Evidence `evidence_7b9168d435714266b547b758a032cb56` was retrieved `2026-09-25T08:21:53.741830+00:00`; capability `overpass_poi_amenities`, provider `overpass`, count 10, status `ok`, not stale, and not truncated. Run `run_956625096e234c1aad0752ac6a67e954` completed in one successful `inspect_evidence` call. The transcript showed every record as `pharmacy`, along with the OpenStreetMap ODbL attribution. The inspection performed no new Overpass fetch and no map plan.

## Saved history and map replay (`T2-06`)

After restarting the backend against the same isolated data directory, a new browser tab loaded saved conversation history. Reopening the earlier saved map conversation restored its transcript, Colosseum viewport, and visible OSM attribution. Saved evidence-inspection tables also appeared in hydrated conversation history. The map run was `run_ec08c4426cd04adeb706dbf072d84873`; it completed using `resolve_geospatial_location` and `apply_map_plan` without calling Overpass. Its trace records `map_prepared`, `run_suspended`, two `render_observed` events, `run_resumed`, and completion.

Visual browser inspection confirmed rendered OpenStreetMap tiles around the Colosseum and visible attribution. The browser controller displayed screenshots inline but did not expose a local screenshot export path in this run; no `browser.png` artifact is claimed.

## Evidence inspection route (`T2-07`)

The exact-lane model inspected the freshly saved POI evidence in one call as `run_956625096e234c1aad0752ac6a67e954`. The transcript showed its evidence ID, retrieval timestamp, source, count, all ten categories, and attribution; no provider fetch or map render occurred. A second same-conversation inspection of `evidence_c0503012ee3341f08546b812911c6d58` also completed in one call as `run_634d9f4e598d4978937deb15ee590155` after backend restart.

## Historical and remaining boundaries

- Historical evidence `evidence_343aa7118f1b4e3ab005bd4221b75e01` contains mixed categories and is retained as historical. The current fresh filtered evidence contains only pharmacies.
- This is selected live evidence, not a complete provider, catalog, raster, recovery, or model-parity matrix.
- Capability discovery remains stopped at the configured `max_model_calls=4` guard; continuation policy is unchanged.
- `T2-04` remains partial at 36/50 candidates. `T0-04` remains partial for paired startup timing, provider outage, ownership-race, and injected-failure cleanup coverage.
- The broader exact-lane route/live matrix remains partial for Acropolis semantics, imagery extent, weather budget, USGS/land-cover aliases, generic-infrastructure clarification, multilingual/provider routes, and Tier 3–5 scenarios.
- FEMA rendered pixels and FEMA overlay composition/retention remain unproven; ESA WorldCover source loading failed and GIBS was upstream-unavailable. These remain partial raster/state-preservation gates under `ISSUE-002`.
- OpenAI/Ollama provider parity remains blocked because required services and approved credentials were unavailable. Credentialed providers and local-source routes remain blocked because approved credentials and configured feeds/snapshots/datasets were unavailable.
- Exact-head hosted CI for this scoped change is pending publication; the historical hosted result is not presented as validation of this source boundary.
