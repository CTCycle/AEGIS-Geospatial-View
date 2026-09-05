# AEGIS end-to-end audit and stabilization report

Audit date: 2026-09-05 (Europe/Rome)
Checkout: `G:\Projects\Repositories\Active projects\AEGIS Geospatial View`
HEAD at audit start: `f2b214c4cc32d8df651c2a35c859e26203aa5b4d`
Configured live model: `opencode-go/deepseek-v4-flash`

Overall outcome: the application is materially more bounded and diagnosable, but the requested robustness claim is not met. The live model lane remains blocked by repeated structured-extraction deadlines, one metadata-only weather response is still described as visible, and one provider-auth response still points users to Model Settings instead of Access. Those limitations are recorded as failed or blocked acceptance criteria below.

## A. Scope, setup, and evidence

The audit used the existing Python environment (`app/server/.venv`, Python 3.14.2), the repository Node runtime (22.23.1), the existing SQLite database, and the configured model without substitution. The frontend was served at `http://127.0.0.1:4512`; the backend was served at `http://127.0.0.1:7059`. Existing local edits were preserved, including the hazard adapter expectation and API units fallback. No migration was required (`current=head=202608310001`).

Evidence is retained under this directory. Baseline and post-fix artifacts use separate names. Browser evidence was captured with the in-app Browser and saved only after the Stop generating control disappeared and the map settled. The controlled browser lane is deterministic and must not be read as live provider compatibility.

## B. Actual architecture and ownership

The request path is Angular chat over a WebSocket to the FastAPI realtime endpoint. The backend persists the conversation and run, assembles bounded context, extracts a structured turn contract, resolves geographic signals, builds a plan, executes direct/native geospatial tools or provider adapters, normalizes provider payloads, persists the response, and merges a revisioned overlay collection. The Angular map owns the MapLibre instance and renders the persisted basemap plus overlay descriptors; candidate maps now wait for `idle` before replacing the current map.

Canonical authorities remain the resolved geographic state, conversation/run persistence, execution budgets, and revisioned overlay collection. Full geometry stays in persisted/provider state rather than being copied into the model history projection. Overlay instance IDs remain derived from capability, scope, and variant.

## C. Provider and native-tool inventory

The inventory contains 86 manifests, 39 providers, 4 direct tools, 5 native LLM tools, and 68 runtime profiles. Direct tools are `get_air_quality_forecast`, `get_nearby_poi`, `get_weather_forecast`, and `location_to_coordinates`. Native tools are capability listing, capability description, capability execution, provider-layer fetch, and provider-layer rendering. `inventory-live.md` and `inventory-live.json` distinguish executable adapters, rendering/catalog-only entries, credential-gated providers, unavailable endpoints, and un-sampled metadata.

The endpoint sample recorded public successes for OpenFreeMap, Census, GIBS, Open-Meteo, OSM tiles, SoilGrids, terrain tiles, and CartoDB; EEA returned 404 and ESA reset the connection. Credentialed providers were not called without keys. The inventory records latency/failure behavior where sampled and marks the rest not sampled rather than inferring health.

## D. Geographic interpretation

Passed live or deterministic evidence includes Rome, EUR in Rome after the resolver and capability boundary fixes, Paris versus Paris Texas, Cambridge ambiguity followed by Cambridge Massachusetts, Milan Michigan correction, Zurich/Lugano switching, Ticino boundary selection, coordinates/bounds, and a direct map-projection question. The resolver now deduplicates hierarchical regional address components; the parser now keeps context for `about`, pronouns, ordinal references, comparison, and `back`; explicit district/region concepts no longer collapse into location-only navigation.

The live 25-turn run still failed the `first city` referent and produced partial border/“around here” responses. Misspellings, non-English names, landmark/address breadth, and multi-location comparison were covered by deterministic fixtures or inventory tests but were not all live-held out with the configured provider.

## E. Rendered workflows and map evidence

`final2-rome-1.png` shows Rome satellite imagery after the map settled. `final2-eur-1.png` shows the repaired EUR district viewport, with the resolved E.U.R. hierarchy in the workspace header. The earlier `baseline-rome.png`, `baseline-eur.png`, and `paris-texas-after.png` are retained for comparison.

Point and polygon/provider-backed paths were exercised in the live 25-turn trace: Amsterdam parks returned a partial point workflow and Ticino returned a Natural Earth boundary overlay. The multi-tool workflow was not isolated post-fix. OpenAQ failure preserved the previous valid Rome map. Weather pressure/humidity/wind reproduced a contract mismatch: the layer panel and legend correctly said metadata-only, while the assistant sentence said `Visible overlays: the Weather Forecast overlay.`

## F. Multi-turn, context, and history

Deterministic 10-, 25-, and 50-turn context sessions passed bounded serialization checks. The 50-turn projection retained 42 messages, omitted 8, projected 7,340 tokens, and preserved exact location facts. Unknown provider/model capacity remains unknown; the application applies a 32,768-token input ceiling for unknown limits and an 8,192-token history ceiling. The UI correctly displays `Context limit unavailable` when no provider limit is reported.

The live 25-turn session took 296.26 seconds. It produced 21 usable responses, four bounded extraction-timeout failures, and no unbounded loop. Turns 2/20 Lugano, 6/7 Rome/EUR, 10 Milan Michigan, 12 Paris Texas, 14 Cambridge Massachusetts, and 21 Ticino were usable. Turns 1, 3, 4, and 19 hit the application deadline during structured extraction. This prevents the live 50-turn extension and the live acceptance pass.

## G. Spatial correctness and provider handling

Unit and controlled-failure coverage includes coordinate order, bounds, geometry normalization, null/invalid payloads, feature IDs, partial/empty responses, provider auth/error classes, raster descriptor handling, URL redaction, and bounded payload behavior. The map candidate swap now commits only after `idle`, so a delayed source error leaves the last valid map in place. Raw provider URLs are sanitized in the map error surface.

Live evidence confirms provider-auth failure is distinct from a valid empty result at the search boundary and preserves the old map. The remaining response text classification issue is isolated to metadata-only overlay summaries; its fix was prepared but could not be applied after the Codex account reached its usage limit.

## H. Lifecycle, cancellation, and recovery

The controlled browser lane passed 20 tests in 72.63 seconds, including orchestration stress, map-render regressions, chat persistence, and ambiguity. Unit coverage passed the cancellation, stale-run, duplicate suppression, revision, reconnect, and conversation-isolation suites. Live rapid-steering and delayed-result behavior were not exhaustively repeated because the live provider lane was already deadline-limited.

## I. Security and observability

Provider request parameters redact key, secret, token, password, and authorization markers. Geometry remains outside model history. Popup and map error paths do not expose raw provider URL/error text after the map error sanitization fix. The trace includes conversation ID, run/request IDs, stage names, status, durations, remaining deadline, location resolution, tool calls, and persistence checkpoints. The runner’s `peak_context_usage_percent=0.0` is treated as an unknown-value default, not measured usage.

## J. Performance findings

The deterministic context projection scales from 1,542 projected tokens at 10 turns to 7,340 at 50 turns while retaining exact location facts. Live structured extraction was the dominant latency and failure point: successful turns generally took 5–18 seconds and deadline failures took approximately 20 seconds. Provider endpoint samples were bounded and recorded in the inventory; no invented latency target is used.

## K. Changes, validation, ratings, and remaining limitations

Implemented changes include bounded unknown-limit context assembly, compact history projections, duplicate-safe location hierarchy assembly, broader contextual parser signals, explicit data-concept capability boundaries, Paris hierarchy correction, OpenAQ provider-backed rendering and failure propagation, idle-gated MapLibre candidate swaps, sanitized map provider errors, configurable E2E artifact roots, and preserved hazard/API fixes. Regression tests were added at each reproduced boundary.

Validation results: backend unit tests 825 passed with 3 warnings; frontend tests 202 passed; Angular build passed; Ruff passed with Windows ACL warnings; full backend Pyright reported 0 errors and 0 warnings; strict catalog audit reported 0 errors; controlled browser E2E passed 20/20; fault benchmark passed 3/3. The live provider lane is blocked, not passed.

Ratings use 1 (evidence of severe failure) through 5 (repeatable evidence across requested lanes). `Not assessed` means evidence was insufficient.

| Dimension | Rating | Evidence boundary |
| --- | ---: | --- |
| Geographic interpretation | 3 | Strong city/district/ambiguity fixtures and several live passes; first-city and broad referents still fail/partial. |
| Loops and timeouts | 2 | Shared deadline stops provider calls; four live extraction deadlines remain. |
| Tool correctness | 3 | Normalization/fault suites pass; weather metadata mismatch remains. |
| Rendering | 3 | Rome, EUR, Paris Texas, and map preservation rendered; dynamic metadata contract failed. |
| Race/lifecycle safety | 4 | Idle-gated candidate swap and controlled lifecycle suite pass. |
| Multi-turn state | 2 | Context signals improved; first-city return and some removal/referent turns remain partial. |
| Context growth | 4 | 10/25/50 deterministic bounds pass; live provider limit is unknown and live 25 is blocked. |
| Recovery | 4 | OpenAQ failure preserves the last valid map; user-facing auth classification needs one patch. |
| Latency | 2 | Successful live turns 5–18s; repeated 20s structured-extraction deadlines. |
| Observability | 4 | Correlated run/tool/layer IDs and stage traces are retained. |

Remaining limitations: response-builder metadata-only filtering is blocked by the current Codex usage limit; provider auth errors from the live UI still mention Model Settings; live 50-turn and isolated multi-tool/browser rapid-steering workflows are unrun; credentialed providers remain unverified; EEA/ESA upstream checks remain unhealthy. These prevent an overall robustness claim.

