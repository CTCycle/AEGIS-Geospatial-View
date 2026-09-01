# AEGIS Geographic-Agent Validation Report

Date: 2026-09-01  
Branch: `develop`  
Final validation commits: `319da265`, `62a345b3`  
Scope: agent interpretation, provider execution, typed state, provenance, frontend map rendering, conversation continuity, and degraded behavior.

## Final assessment

AEGIS is reliable for the currently catalog-backed location, map, POI, weather, and supported geospatial-data flows. The final live browser run verified real Rome weather, a real OpenStreetMap/Overpass hospital search, feature inspection, and a weather follow-up that reused the prior location. Unsupported domains remain fail-closed rather than fabricated.

It should not be described as a universal geographic data agent yet. Crime and real-estate values have no reliable enabled source, the weather map overlay is intentionally metadata-only, and the complete 24-scenario live model-in-loop batch was not run because it would require a longer and more expensive live provider run. Deterministic contract coverage plus targeted live validation passed; the remaining limitation is coverage breadth, not a known blocker in the verified workflows.

## Architecture observed

The implemented request lifecycle is:

1. Angular `GeospatialPageComponent` collects the user turn, persists page state, and calls `/api/chat/turn` plus the conversation realtime channel.
2. `AgentOrchestrator` loads recent history, durable task state, location memory, active visualization state, and active instructions through the context/history services.
3. `ParserService` requests typed structured extraction from the configured model, normalizes intent, locations, coordinates, viewport, temporal signals, requested concepts/layers, POI categories, overlay commands, ambiguities, and parser failures.
4. Conversation history merges explicit deictic references with the remembered active location. A deterministic language-boundary supplement recognizes omitted `there`, `here`, nearby, same-area, and equivalent references without inferring a place name or provider.
5. `CapabilityResolver`, policy preflight, and the catalog/runtime registries constrain the request to enabled capability identities and reject unsupported or unsafe interpretations.
6. `DeterministicToolPlanner` creates a dependency-aware plan. `ToolPlanExecutor` executes native tool calls with validation, bounded retry policy, duplicate-call fingerprints, and structured error propagation.
7. `AgentToolCatalogService`, `LocationResolver`, Nominatim, Open-Meteo, Overpass, and other registered providers perform the external work. Provider responses are normalized into typed map/direct-result envelopes with provenance.
8. `AgentTurnStateAssembler` combines verified tool output, direct measurements, map sessions, provider events, overlay mutations, evidence, and warnings. It does not re-query a provider when a complete verified map result already exists.
9. `ConversationTaskStateService` persists completed task state, resolved locations, viewport/CRS, layer references, source references, evidence references, and renderable map-session state before synthesis.
10. Grounded response synthesis receives the completed task and verified operation. Unsupported, failed, partial, and metadata-only results are explicitly distinguished from observations.
11. The typed `ChatTurnResponse` reaches Angular. `api-parsers` normalizes the payload; `MapPreviewComponent` derives MapLibre basemaps, GeoJSON/raster/vector-tile/metadata-only layers, legends, attribution, inspections, and render-state errors.
12. Subsequent turns reuse only the relevant persisted context. A new chat clears map state and now also clears any feature inspector that no longer belongs to the active map session.

Structured observability is present at `chat_turn_start`, `parser_extract`, `parser_normalized`, `chat_turn_parsed`, `chat_turn_plan`, `location_resolved`, `map_request_built`, `planned_chat_turn_complete`, and `chat_turn_complete`. Responses and benchmark traces retain the parsed contract, plan, arguments, tool results, provider events, task snapshot, map session, and grounding/provenance evidence.

## Tests performed

Automated gates run against the final code:

- Backend unit and agent-benchmark contracts: `658 passed, 2 warnings`.
- Angular client suite: `191 SUCCESS`.
- Angular geospatial smoke suite: `5 SUCCESS`.
- Scripted fault lane (`timeout`, malformed provider response, invalid geospatial arguments): `3/3 passed`, zero unnecessary tool calls.
- Live provider smoke against the running backend: `1/1 passed`, provider reachable, provenance present, rendering expectations satisfied.
- Ruff on changed Python files: all checks passed.
- `git diff --check`: passed for staged changes.

The repository-wide `app/tests` invocation was not used as a gate because it also attempted the broader E2E harness with its default-port/protected temporary-directory assumptions. The authoritative backend gate is the explicit `app/tests/unit app/tests/agent_benchmark` command above; no unrelated E2E harness failure was treated as an application defect.

The evaluation manifest contains 28 representative scenario IDs across 24 model-in-loop prompts, 3 scripted-fault scenarios, and 1 live-provider scenario. It covers physical geography, weather, air quality/land cover, POIs/transit, population, unsupported property/crime, ambiguity, scale, temporal requests, compound/multi-tool plans, follow-ups, and corrections. The 24 model-in-loop cases are retained for repeatable future live evaluation; only the targeted live smoke was run in this validation window.

## Problems discovered and corrected

| Severity | Symptom and root cause | Affected layer | Result |
|---|---|---|---|
| High | A successful provider map result was assembled and then queried again while building final state. The second snapshot could differ and caused duplicate provider work. | Orchestration/provider boundary | Reuse the single validated map session; regression coverage checks single execution. |
| High | Synthesis observed the pre-execution task snapshot and could claim that no result existed. | Task state/synthesis | Persist completed task state before synthesis and guard final prose against unsupported “no result” contradictions. |
| High | A direct provider measurement could disappear when a map session was also present. | Result envelope/frontend contract | Preserve direct result and map session as separate typed outputs. |
| High | Nested provider measurements were hidden by shallow evidence extraction. | Provider normalization | Recursively retain nested measurements and their provenance. |
| High | Basemap attribution could overwrite the provider attribution for a data capability. | Provenance | Make provenance capability-scoped and preserve provider/source/fetch metadata. |
| High | The model sometimes omitted an explicit POI category, allowing an underspecified layer choice. | Parser/catalog boundary | Recover only catalog-declared categories when the parser already identified a POI request; route them through the generic layer contract. |
| High | A context-query label could short-circuit an actionable follow-up. | Parser/orchestration | Typed executable intent takes precedence over context shortcuts. |
| Medium | Generic action words were treated as dataset identities. | Capability resolution | Resolve dataset identity from catalog semantics, not arbitrary action tags. |
| High | Provider failure or unsupported data could be represented as an apparently usable map. | Failure/result/rendering contracts | Fail closed: no unverified geometry, values, or map overlay is synthesized from a failed call. |
| High | Location-only provider work was not always represented as execution evidence or durable geospatial state. | Observability/task state | Add typed Nominatim provenance, first-class `location_resolution` provider events, and state projection for location/evidence/viewport. |
| Medium | A feature inspector from a prior map remained visible over a new chat. | Angular map state | Reconcile the selected inspection against the active overlay collection and clear it when the session changes. |
| High | The live model omitted the deictic signal for “What is the current temperature there?”, so memory resolution never ran. | Parser/language boundary | Add general deterministic deictic phrase recovery, excluding existential “there is/are” constructions; the live follow-up now preserves Rome. |

Earlier live runs also exercised a real transient provider timeout and a synthesis timeout. The system returned a transparent degraded response and diagnostic rather than inventing geographic data.

## Changes implemented

The changes are incremental and systemic rather than prompt-specific:

- tightened typed parser, location, temporal, POI, overlay, and persisted-task contracts;
- added catalog-backed capability identity and dependency-aware planning;
- added provider provenance, source URLs, retrieval timestamps, observation metadata, coverage, units, and result status;
- made tool execution and provider failure validation fail closed;
- grounded synthesis and map rendering in completed verified task state;
- preserved direct data beside map sessions and recursively retained nested provider payloads;
- added first-class provider events for work such as geocoding that is not itself a native tool call;
- standardized frontend map-session derivation, render-state failures, metadata-only behavior, inspections, legends, attribution, and stale-session cleanup;
- added the evaluation matrix and deterministic fault lane;
- refreshed `app/shared/openapi.json` from the current typed backend schema;
- added regression coverage for omitted deictic references and stale feature-inspector state.

The last two validation discoveries were committed and pushed separately:

- `319da265 fix: reset map inspection on session replacement`
- `62a345b3 fix: recover omitted deictic references`

## Data validation

Real external integrations validated:

- Overpass/OpenStreetMap through the actual browser UI: `Find hospitals within 5 km of Rome, Italy.` returned 30 hospital points, stated the 5,000 m circular coverage, rendered clustered points on the satellite basemap, showed OSM attribution, and exposed a selected feature with category `hospital`, provider `overpass`, status `ok`, freshness timestamp, and the approved Overpass source link.
- Open-Meteo through the actual browser UI: Rome resolved to approximately `41.8933, 12.4829`; the final direct answer reported `30.4°C` at `10:45` local time on 2026-09-01, clear conditions, no precipitation, Celsius units, and the Open-Meteo source. The follow-up “there” reused Rome and returned the same provider-backed observation.
- Nominatim through the live provider smoke: Zurich resolved to `47.3744489, 8.5410422` with bbox `[8.4480182, 47.3202187, 8.6254529, 47.434665]`, provider `nominatim`, source URL, fetch timestamp, `result_status=ok`, and `result_type=location`.
- Esri World Imagery rendered as the selected satellite basemap in the live map screenshots; OSM and provider attribution remained visible.

The validation checked coordinate ordering, bbox ordering, radius semantics, provider identity, source URL, freshness/status, units, direct-vs-rendered distinction, and empty/metadata-only behavior. Weather was deliberately not represented as a false live raster: the UI labels the forecast overlay `metadata-only` and states that the numeric observation came from the direct provider result.

## Agent behavior

- Intent extraction: typed task class, normalized action, concepts, layers, POI categories, temporal signals, viewport, and tool-needed status are captured before execution.
- Geographic extraction: explicit coordinates and provider geocoding are supported; memory resolution is used only for recognized deictic references with valid remembered coordinates.
- Clarification: Springfield and fresh deictic requests without usable memory produce clarification instead of confident guesses. Clear named cities, coordinates, and radius requests do not require unnecessary clarification.
- Tool selection: catalog identity and capability families constrain selection; the hospital flow used the generic geospatial capability with the Overpass POI category, and duplicate successful map execution was removed.
- Tool arguments: validated envelopes preserve capability IDs, nested arguments, location/radius/bbox, temporal semantics, and provenance. Malformed and invalid arguments are rejected in the scripted lane.
- Multi-tool execution: the planner and executor support dependency levels, input/output references, partial-failure policy, and combined results. Compound/multi-tool scenarios are in the evaluation matrix and contract tests; a complete live batch of every compound prompt remains future work.
- Result synthesis: final text is built from verified operation/task state, with explicit provider attribution and explicit limitation language for unavailable data.

## Rendering validation

The final browser captures verify:

- clustered hospital points in the Rome area with a visible legend and provider attribution;
- feature inspection with real name/category/source/status/freshness data;
- satellite basemap and correct coordinate-centered map viewport;
- direct weather text beside a clearly labeled metadata-only weather layer;
- follow-up weather text with no stale hospital inspector and preserved Rome context;
- prior ambiguity and unsupported-data captures showing concise clarification and limitation behavior.

Evidence files are under `assets/QA/live-validation-20260901c/`:

- `hospital-map-final.png`
- `hospital-feature-details-final.png`
- `weather-direct-final.png`
- `weather-followup-final.png`
- `ambiguity-clarification.png`
- `unsupported-limitation.png`
- `backend.stderr-live-final8.log`

## Remaining limitations

- No reliable enabled source currently supports crime rates/incidents or real-estate/property prices; the correct behavior is an explicit limitation.
- Open-Meteo direct observations are verified, but the current weather forecast map layer is metadata-only and does not render a live weather raster.
- Provider availability, timestamps, rate limits, and live model output remain time-dependent; the deterministic suite must remain the primary regression gate.
- The full 24-prompt live model-in-loop batch, exhaustive provider cross-checking for every domain, and large-result performance profiling were not completed in this validation window.
- Some external provider schemas remain capability-specific; adding new datasets requires a typed catalog descriptor, normalization contract, provenance mapping, and render contract rather than relying on generic prose.

## Regression coverage

Regression coverage now protects:

- parser schema correction and provider failure contracts;
- explicit coordinates, ambiguous/deictic locations, remembered-location resolution, and omitted deictic recovery;
- capability identity, POI category recovery, tool-plan dependencies, retry/fault handling, duplicate-call prevention, and provider provenance;
- direct-result plus map-session preservation, nested measurement evidence, completed-task grounding, and durable geospatial state projection;
- map session parsing, CRS/bbox/viewport handling, valid GeoJSON/raster/vector-tile modes, metadata-only layers, attribution, layer failures, inspection provenance, and stale inspection cleanup;
- 28 evaluation-matrix scenario classes plus the 3 deterministic degraded-provider scenarios;
- final Angular geospatial browser smoke and live UI screenshots.

## Evidence locations

- Evaluation metrics: `assets/QA/agent-validation-20260901/scripted-fault-final2/metrics.json` and `assets/QA/agent-validation-20260901/live-provider-final4/metrics.json`.
- Live provider trace: `assets/QA/agent-validation-20260901/live-provider-final4/benchmark.json`.
- Final browser/backend trace: `assets/QA/live-validation-20260901c/backend.stderr-live-final8.log`.
- Source changes and regression tests are in the pushed commits listed above and the preceding incremental commits on `origin/develop`.
