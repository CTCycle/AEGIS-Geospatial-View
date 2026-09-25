# Project Status Ledger

Last updated: 2026-09-25

This is the canonical high-level catalog of the current operational state of
AEGIS Geospatial View. The 2026-09-23 T1-03 continuation began from clean
`develop` at `35d04f8399d0166d1a134ad9f45931bc15efda91`, matching
`origin/develop`. The T1-02 test remains scoped to its original
`8375fe071823e7f844f6bb125d86d6ebf36b3110` base plus the working-tree source
hashes recorded in its report; those exact source changes were subsequently
committed at `35d04f8`. The T1-03 report records its own tested source delta.
The T0-01 report remains scoped to `loop-dev` at
`5bb8d416da80e33a7e85b02538f605ee22aee0a5`, an ancestor of `develop`.
Detailed reports explain how a status was established, while this ledger
records the current conclusion.

The 2026-09-24 exact-head validation recheck also began from clean `develop` at
`66008da15ea4ea23a5b1e99090441438bb163fba`, matching `origin/develop`. It
revalidated focused routing and controlled map-render acknowledgement gates;
the exact provider/model browser lane remained unavailable in the isolated
runtime. See the [exact-head recheck report](../QA/tier2-validation-develop-20260924-head66008da/report.md).

The 2026-09-25 follow-up used the user-configured exact `opencode-go / deepseek-v4.1-flash` lane in a disposable isolated runtime. `T2-04` now passes the complete 50-candidate discovery inventory after the approved temporary six-call budget was restored to four; `T0-04` remains partial only for the unavailable safe historical timing comparator. See the [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md) and [browser evidence](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md).

**Current project posture: `PARTIAL`.** The native runtime and core browser
interaction paths have meaningful local and manual proof. The complete live
geospatial matrix, several public-provider routes, live raster rendering,
and some optional integrations remain incomplete or unvalidated. Exact-head
hosted CI passed for the T1-09 implementation commit; each later pushed change
requires its own hosted result.

## Purpose and document roles

Use this ledger for the current answer to “what works, what is incomplete, and
what should happen next?”. It is intentionally compact and is not a debugging
diary or a replacement for detailed validation reports.

- [`project_index.md`](project_index.md) is the documentation entry point and
  defines the ontology and reading order.
- [`validation/gate_status.md`](validation/gate_status.md) remains the detailed
  validation-gate matrix for native-loop, browser, provider, migration, and
  hosted-CI evidence. Its gate taxonomy is intentionally narrower than this
  ledger's component taxonomy.
- [`validation/strategy.md`](validation/strategy.md) is the durable digest of
  the ordered Tier 0–5 validation campaign and evidence rules.
- [`validation/tier1_application_foundations.md`](validation/tier1_application_foundations.md)
  defines the first application-foundations tier and its continuation boundary.
- [`geospatial/native_harness_bootstrap.md`](geospatial/native_harness_bootstrap.md)
  records the native-agent implementation plan and local proof boundaries.
- Dated reports under [`../QA/`](../QA/) contain scenario-level evidence,
  screenshots or logs when available, and long remediation narratives.
- Architecture, runtime, provider, UI, and testing documents describe the
  intended contracts. They do not override a newer status or evidence entry in
  this ledger.

## Maintenance rules for future agents

1. Inspect this ledger before substantial implementation or validation work.
2. Use it to identify known defects and previously validated behavior.
3. Update affected entries after implementation changes.
4. Update validation evidence after meaningful tests or browser runs.
5. Never mark a component `VALIDATED` without supporting evidence.
6. Downgrade a status when a regression is discovered.
7. Close or archive an issue only after remediation and successful
   revalidation.
8. Do not create duplicate issue entries for the same underlying defect.
9. Link detailed reports instead of copying large reports into this ledger.
10. Keep the ledger synchronized with the actual repository and runtime state.

For map claims, rendered browser state is authoritative: a provider response,
HTTP success, descriptor, or visible canvas alone is not proof of a rendered
map. A meaningful map validation needs the expected location and viewport,
visible tiles and attribution, required source/layer state, and a matching
`map.render_ack` where the workflow requires it.

## Status taxonomy

Statuses describe component state, not issue severity. Use exactly one status
per component entry.

| Status | Meaning | Evidence boundary |
| --- | --- | --- |
| `VALIDATED` | Implemented and confirmed through meaningful testing. | The stated scope has current unit, integration, E2E, or manual evidence. |
| `WORKING` | Believed to work from implementation or limited testing, but not fully validated. | Do not treat this as release or complete-matrix proof. |
| `PARTIAL` | Implemented but incomplete, degraded, or valid for only part of the expected behavior. | The limitation is stated concretely in the row or an issue. |
| `BROKEN` | Known not to work correctly for the stated scope. | A concrete failure and evidence reference are required. |
| `BLOCKED` | Cannot currently be validated or completed because of an external dependency, missing credential, unavailable service, hardware constraint, or similar blocker. | Name the blocker; do not convert it into a defect without evidence. |
| `UNVALIDATED` | Implementation exists, but available evidence is insufficient to claim that it works. | This is validation debt, not an automatic failure. |
| `NOT_IMPLEMENTED` | The expected capability is currently absent. | Link the scope document or runtime declaration that establishes the boundary. |
| `DEPRECATED` | Intentionally retained only for compatibility or scheduled for removal. | Link the replacement or removal plan. |

## Implemented, observed, and formally validated

These distinctions prevent code existence from being mistaken for proof.

- **Implemented:** source, manifests, contracts, or architecture describe the
  capability. This supports `WORKING` or `UNVALIDATED`, not `VALIDATED` by
  itself.
- **Observed working:** a limited manual run, focused test, or provider probe
  showed the behavior. This may support `WORKING` or `PARTIAL` when the scope is
  narrower than the product claim.
- **Formally validated:** meaningful automated or browser evidence covers the
  stated behavior and its important failure boundary. This supports
  `VALIDATED` only for that stated scope.

## Current component ledger

### Runtime, backend, and agent

| Component | Status | Scope | Evidence | Known Issues | Blocker | Last Validated | Validation Level | Related Docs | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `runtime.startup.windows-local` | `PARTIAL` | Windows launcher port-consent guard, warm dependency/build reuse, concurrent backend/frontend startup, isolated no-op database startup, and fail-closed cleanup. | The exact-head follow-up records four successful official-launcher starts in the isolated runtime; the simulated provider-outage startup test, changed-owner/PID-reuse protection, injected backend/frontend readiness-failure cleanup, canonical-state protection, and final port cleanup all pass. | No safe same-machine historical before/after timing comparator is available; the observed 103,910 ms sample is retained without turning it into a product defect. Angular `ng serve` still compiles at launch. | — | 2026-09-25 | E2E + automated | [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [timing results](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/timing-results.md), [safety harness](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/launcher-safety-harness.json), [startup](runtime/startup.md) | Preserve the functional startup safety boundary; revisit timing only with a safe paired baseline. |
| `catalog.manifests-and-auditor` | `VALIDATED` | Runtime catalog loading and strict production manifest audit. | Latest focused report records 86 manifests, 0 errors, and 0 warnings. | Catalog coverage is not the same as live-provider or browser-render proof. | — | 2026-09-20 | integration | [manifest contract](geospatial/manifests/manifest_contract.md), [ingestion validation](geospatial/ingestion/validation.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Re-run the strict production auditor after manifest or runtime-profile changes. |
| `backend.agent.native-loop` | `VALIDATED` | Native route, typed tool exposure, observation/recovery cycle, bounded context, and terminal completion contracts. | The 2026-09-25 regression passed 115 focused tests and the full 420-test backend CI selection locally; strict Pyright reports 0 errors/warnings/informations. The selected exact lane completed coordinate, direct forecast, saved-evidence inspection, and map-handoff scenarios. Exact-source hosted CI run `36116073402` passed all four jobs after fixing strict typing and regenerating the shared OpenAPI enum. | Live provider and full-browser scenario coverage remain separate; one live AQ run recovered from a model-generated semantic argument rejection. | - | 2026-09-25 | integration/E2E | [2026-09-25 report](../QA/tier2-validation-develop-20260925-next-slices/report.md), [browser evidence](../QA/tier2-validation-develop-20260925-next-slices/browser-evidence.md), [native harness](geospatial/native_harness_bootstrap.md), [gate ledger](validation/gate_status.md), [2026-09-24 focused report](../QA/tier2-validation-develop-20260924-head77c5d67/report.md) | Re-run the focused native suite after agent-loop, route, policy, or tool changes; rerun hosted CI on future source or test changes. |
| `backend.run-lifecycle-and-persistence` | `VALIDATED` | SQLite migrations, revisioned conversation state, durable run events, terminal finalization, and last-known-good presentation preservation. | Migration and terminal-presentation gates are passing in the detailed validation ledger. | No current defect is evidenced in the tested local scope. | — | 2026-09-17 | integration | [persistence](architecture/persistence.md), [native harness](geospatial/native_harness_bootstrap.md), [gate ledger](validation/gate_status.md) | Re-run isolated Alembic and run-lifecycle tests after schema or persistence changes. |
| `backend.api.sync-chat-turn` | `VALIDATED` | Synchronous chat-turn response boundary and orchestration behavior. | The [T1-06 report](../QA/tier1-validation-develop-20260923/T1-06/report.md) records the exact-lane live `200/202/409/404/503` matrix, 14 focused API/OpenAPI tests, and 397 corrected backend CI tests. | No current T1-06 defect is evidenced; completed-event hydration now removes run-only state and restores omitted nullable context usage before response validation. | — | 2026-09-23 | integration | [T1-06 report](../QA/tier1-validation-develop-20260923/T1-06/report.md), [backend API](architecture/backend_api.md), [gate status](validation/gate_status.md) | Preserve status distinctions and safe error detail when the chat route or run lifecycle changes. |
| `model.opencode-go.deepseek-v4.1-flash` | `VALIDATED` | Exact configured provider/model lane readiness and visible selection without silent fallback. | The 2026-09-25 final isolated-runtime Settings probe returned `Verified` and `Native tool probe passed`; the T2-04 browser run used the exact lane without fallback, and the runtime setting was restored to 4 after restart. See the [follow-up browser evidence](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md). The 2026-09-19/20 browser reports also observed the exact lane. | Readiness does not prove every geospatial scenario or provider parity. | — | 2026-09-25 | E2E | [configuration](runtime/configuration.md), [gate ledger](validation/gate_status.md), [follow-up browser evidence](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md) | Preserve the exact lane in future revalidation and record any provider change explicitly. |
| `model.provider-parity.openai-ollama` | `BLOCKED` | Provider-specific continuation and structured-output proof outside the exercised OpenCode Go lane. | Native implementation documents say OpenAI Responses and Ollama remain unrun; the live boundary retains Ollama-unavailable behavior rather than falling back. | No current parity claim is allowed. | Required provider credentials/services were not available for the recorded validation boundary. | — | None | [native harness](geospatial/native_harness_bootstrap.md), [configuration](runtime/configuration.md), [gate ledger](validation/gate_status.md) | Run provider-specific continuation probes when each service and approved credential is available. |
| `agent.capability-routing.live-language` | `PARTIAL` | Natural-language routing and capability discovery for keyless geospatial requests. | The 2026-09-25 focused five-file regression passes 83 tests in this follow-up, while the earlier focused continuation covers the broader route set. The exact-lane browser run now completes the bounded 50-candidate discovery inventory without a map; direct tools, saved-history hydration, and saved-evidence inspection remain separately evidenced. | `ISSUE-006` and remaining gaps: Acropolis semantics, imagery extent, weather budget, USGS/land-cover aliases, generic-infrastructure clarification, and broader route-family coverage. One AQ live run recovered from a model-generated argument validation rejection; Overpass reports partial reliability and bounded coverage. | — | 2026-09-25 | E2E + automated | [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [browser evidence](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md), [2026-09-25 report](../QA/tier2-validation-develop-20260925-next-slices/report.md), [focused suite](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/focused-suite.log) | Preserve the completed inventory boundary and continue the remaining route matrix with exact source, coverage, and render evidence. |
| `agent.capability-discovery.inventory` | `VALIDATED` | Bounded runtime catalog pagination, result semantics, and discovery-only completion without map rendering. | The exact-lane browser run completed five successful pages (`12+12+12+12+2`) for 50 candidates, 50 unique IDs, and final `next_cursor=null`; the map session remained empty and six model calls stayed within the approved isolated `max_model_calls=6` budget. The setting was restored to `4` after restart. | This proves the bounded inventory slice only; it does not validate every provider, route family, renderer, credentialed source, or raster layer. | — | 2026-09-25 | E2E + automated | [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [browser evidence](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md), [run trace](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/inventory-run-trace.json), [focused suite](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/focused-suite.log) | Re-run after catalog pagination, runtime-budget, or discovery-route changes; keep provider and map-render boundaries separate. |
| `agent.location-resolution.core` | `VALIDATED` | Direct locations, clarification, invalid-coordinate bounds, safe recovery, and repeated location changes. | Exact-lane browser evidence passes Florence clarification while retaining Rome, canonical Milan/Texas ambiguity labels, and explicit Milan, Italy rendering. Prior Zurich bounds rejection and Springfield clarification remain linked evidence. | Other language and geography combinations remain part of the broader partial route matrix. | — | 2026-09-24 | E2E | [current browser evidence](../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [prior core report](../QA/core-behavior-e2e-20260919/final-report.md), [agentic search](geospatial/agentic_search.md) | Preserve clarification-before-replacement and canonical locality/region/country labels; broaden only through the exact-lane matrix. |
| `agent.location-resolution.landmarks` | `VALIDATED` | Landmark-centric location resolution and nearby-amenity routing. | Current T2-03 browser runs resolved the Colosseum and clarified central Rome to the correct Italy location, discovered `overpass_poi_amenities`, rendered the layer, and received browser acknowledgement. | Overpass reports partial reliability and roughly 2.5 km coverage; the broad keyless capability matrix remains `PARTIAL`. | — | 2026-09-23 | E2E | [T2 retry report](../QA/tier2-validation-develop-20260923-retry/report.md), [browser evidence](../QA/tier2-validation-develop-20260923-retry/browser-evidence.md), [agentic search](geospatial/agentic_search.md) | Expand to the remaining landmark and POI catalog routes without promoting provider-reported counts to independent ground truth. |
| `agent.map-render-ack-recovery` | `PARTIAL` | Candidate map preparation, browser acknowledgement, failed-render recovery, supersession, and last-known-good preservation. | The saved-evidence Colosseum map run `run_ec08c4426cd04adeb706dbf072d84873` completed after browser render observations and was visible again after history hydration, with OpenStreetMap attribution. At `develop@66008da`, the visible MapLibre module also passes its happy path and all eight controlled fault cases; live FEMA/ESA sources still fail their separate checks. | `ISSUE-002`: public raster source failures remain. | Public source-load behavior and last-known-good behavior with those public overlays prevent a complete claim. | 2026-09-25 | E2E | [2026-09-25 browser evidence](../QA/tier2-validation-develop-20260925-next-slices/browser-evidence.md), [exact-head controlled module](../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/full-module.log), [exact-head recheck report](../QA/tier2-validation-develop-20260924-head66008da/report.md), [gate ledger](validation/gate_status.md), [hazard rerun](../QA/aegis-hazard-hydrology-e2e-20260920/report.md) | Investigate FEMA/ESA source loading and validate composition/retention with browser-visible public overlays; keep the controlled acknowledgement module passing. |

### Geospatial data, maps, and integrations

| Component | Status | Scope | Evidence | Known Issues | Blocker | Last Validated | Validation Level | Related Docs | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `providers.normalized-adapters` | `PARTIAL` | Provider registry, normalized feature/raster/metadata responses, attribution, stale/empty/error semantics, and selected live adapters. | The 2026-09-25 live run verified a pharmacy-only Overpass query with ten `pharmacy` records, `ok`/not-stale/not-truncated evidence, and visible OSM attribution; the exact lane also returned 24-row Open-Meteo weather and air-quality windows. Focused adapter regressions are included in the 115-pass current five-file suite. | FEMA retrieval works but its raster does not load in MapLibre; GIBS was upstream-unavailable; Census and several cataloged paths remain incomplete. The Overpass provider continues to advertise partial general reliability. | — | 2026-09-25 | E2E + automated | [2026-09-25 report](../QA/tier2-validation-develop-20260925-next-slices/report.md), [browser evidence](../QA/tier2-validation-develop-20260925-next-slices/browser-evidence.md), [provider framework](geospatial/providers/provider_framework.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Run the broader provider smoke matrix and preserve distinct upstream, routing, credential, and renderer outcomes. |
| `maps.basemap-switching` | `VALIDATED` | Supported basemap rendering, switching, manual preference preservation, and return to a stable map. | Core browser report verified supported basemap switches and Dark-basemap persistence across ten location changes. | Reload/new-chat reset to the documented catalog default by design. | — | 2026-09-19 | E2E | [frontend architecture](architecture/frontend_architecture.md), [state preservation](ui/state_preservation.md), [core report](../QA/core-behavior-e2e-20260919/final-report.md) | Re-run the switch/persistence flow after renderer or session-state changes. |
| `maps.vector-overlays` | `VALIDATED` | Demonstrated GeoJSON/point/line/polygon overlay rendering and visible attribution for selected public paths. | Residential buildings, earthquakes, coastal stations, atmospheric points, USGS gauges, Census hydrography, and NOAA valid-empty behavior passed in recent live runs. | This is a demonstrated subset, not proof of the complete catalog. | — | 2026-09-20 | E2E | [frontend architecture](architecture/frontend_architecture.md), [geospatial validation](geospatial/ingestion/validation.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Expand the matrix while keeping visible source/layer and acknowledgement evidence for every map claim. |
| `maps.raster-overlays` | `PARTIAL` | Raster, WMS, and WMTS descriptor execution through the real MapLibre renderer. | NOAA radar rendered and acknowledged; FEMA retrieval succeeded but source loading failed; ESA WorldCover source loading failed; GIBS was unavailable upstream. | `ISSUE-002`: no verified FEMA or WorldCover pixels in the affected runs. | Public source-load/provider boundaries remain unresolved. | 2026-09-20 | E2E | [provider framework](geospatial/providers/provider_framework.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md), [hazard rerun](../QA/aegis-hazard-hydrology-e2e-20260920/report.md) | Investigate the failing public source/layer boundary without weakening `map.render_ack`; rerun FEMA, ESA, and GIBS cases. |
| `maps.state-preservation` | `PARTIAL` | Overlay removal, visible-state narration, basemap preference, composition, and retaining an existing overlay during changes. | Working USGS removal and committed-state narration passed; FEMA + USGS composition and FEMA retention remain blocked because FEMA never rendered. | `ISSUE-002`: retention of an unrendered FEMA overlay is not proven. | FEMA raster render is required before the composition and retention flows can complete. | 2026-09-20 | E2E | [state preservation](ui/state_preservation.md), [hazard rerun](../QA/aegis-hazard-hydrology-e2e-20260920/report.md) | Re-run composition and selective removal only after a verified FEMA source/layer acknowledgement. |
| `providers.credentialed-and-local-source-access` | `BLOCKED` | Credentialed providers and configured local feeds or snapshots such as OpenAQ, TomTom, OpenTripMap, Windy, Google Maps, ArcGIS, NASA FIRMS, GTFS, Overture, Open Charge Map, and local cameras. | Recent live reports explicitly excluded these paths because required credentials, snapshots, feeds, or local datasets were absent. | Absence in this environment is not an application defect. | Approved credentials and/or configured local source artifacts are unavailable. | — | None | [access overview](geospatial/providers/access_overview.md), [provider sources](geospatial/providers/public_and_optional_sources.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Configure only approved sources, then run the dedicated provider and browser checks without exposing secrets. |
| `geospatial.dataset-ingestion` | `UNVALIDATED` | Dataset-ingestion manifests, CSV/GeoJSON materialization, checksums, source health, and optional heavy-format handling. | Contracts and validation workflow are documented; no recent convincing end-to-end ingestion run is recorded in the current QA set. | Heavy GIS formats are intentionally optional and may remain partial. | — | — | None | [dataset ingestion](geospatial/ingestion/dataset_ingestion.md), [ingestion validation](geospatial/ingestion/validation.md) | Run a representative isolated ingestion workflow and record its artifact and source-health evidence. |

### UI, quality, delivery, and coverage

| Component | Status | Scope | Evidence | Known Issues | Blocker | Last Validated | Validation Level | Related Docs | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ui.chat-map-workspace` | `VALIDATED` | Startup-to-chat flow, clarification, map controls, transcript hygiene, recovery, and repeated core location use. | Current exact-lane evidence shows Rome transcript/map, Florence clarification before replacement with visible acknowledgement, and canonical Milan choices followed by an attributed, acknowledged Italy map. DSML protocol-looking finalizer content remains suppressed. | Broad route families, source/raster behavior, and complete provider/browser coverage remain separate partial gates. | — | 2026-09-24 | E2E | [frontend architecture](architecture/frontend_architecture.md), [core report](../QA/core-behavior-e2e-20260919/final-report.md), [current T2 report](../QA/tier2-validation-develop-20260924-head77c5d67/report.md), [browser evidence](../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md) | Keep location clarification, visible `map.render_ack`, attribution, and transcript hygiene in the browser smoke. |
| `ui.settings-provider-access` | `VALIDATED` | Settings sections for model selection, model-provider credentials, local runtime, geospatial access, and persisted application runtime configuration. | T1-09 navigation/drafts and T1-10 credential lifecycle both pass. T1-10 validates masked state, safe model/geospatial save and clear, blank/invalid drafts, unreadable credentials, API failures, and the targeted selected-model response. See the [T1-10 report](../QA/tier1-validation-develop-20260923/T1-10/report.md). | Live provider authentication/connectivity remains outside this UI gate and is tracked separately as blocked provider access/parity. | — | 2026-09-23 | integration/E2E | [frontend architecture](architecture/frontend_architecture.md), [access overview](geospatial/providers/access_overview.md), [user settings](user/settings_and_access.md), [runtime validation](../QA/settings-runtime-validation-20260921.md), [T1-09 report](../QA/tier1-validation-develop-20260923/T1-09/report.md), [T1-10 report](../QA/tier1-validation-develop-20260923/T1-10/report.md) | Continue campaign at T2-01; rerun the Settings flow after credential UI or API contract changes. |
| `validation.application-foundations-tier1` | `VALIDATED` | Tier 1 route, state, conversation, realtime, run, API, jobs, Settings, credential, model, and context foundations. | T1-10 passed on `develop@8e32f82e3f094e5fb17c3978fad69b9f80b7af0b`; Tier 1 remains 12 `PASS`. The current campaign roll-up is 23 `PASS` / 1 `PARTIAL` / 0 `BLOCKED` / 44 `UNRUN` after the T2-04 inventory completion. The historical implementation and generated API contract at `develop@7685cce7e23c5d4cb9edd603a8b49d3ef5aaa8d9` passed all four jobs in [hosted CI run 36051868085](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36051868085); the follow-up evidence head `db5b9485e80073f87dd4a8b964e484ba42384fcb` also passed all four jobs in [hosted CI run 36152093449](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36152093449), with implementation source still tested at `800e0568f6b83254b60c4efe25e014e3fefdf81c`. | `T0-04` remains partial for its timing comparator; broader downstream live/browser/provider coverage remains open. | - | 2026-09-25 | integration/E2E | [validation strategy](validation/strategy.md), [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [T2-04 browser evidence](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md), [Tier 1 checklist](validation/tier1_application_foundations.md), [T1-10 report](../QA/tier1-validation-develop-20260923/T1-10/report.md) | Complete the remaining partial and unrun slices while keeping browser, provider, and exact-head CI boundaries distinct. |
| `quality.pyright-strict` | `VALIDATED` | Strict repository-wide Python typing gate. | The current Tier 0 sweep reports 0 errors, 0 warnings, and 0 informations under `app/server/pyproject.toml`; Python source compilation also passed for 410 files. | — | — | 2026-09-22 | integration | [Tier 0 final report](../QA/tier0-validation-develop-20260922/final/report.md), [testing and quality](coding/testing_and_quality.md), [gate ledger](validation/gate_status.md) | Rerun the full strict project configuration after typing or project-configuration changes. |
| `quality.ruff-and-frontend-regressions` | `VALIDATED` | Repository-wide Ruff, Angular production build, frontend state helper, and Karma regression suite. | The current Tier 0 sweep passes Ruff, 19 frontend-state tests, the Angular production build, and 248/248 Karma tests. | Existing frontend sanitizer/deprecation diagnostics remain non-failing warnings. | — | 2026-09-22 | integration | [Tier 0 final report](../QA/tier0-validation-develop-20260922/final/report.md), [testing and quality](coding/testing_and_quality.md), [gate ledger](validation/gate_status.md) | Rerun the relevant frontend suite when frontend or shared contract files change. |
| `validation.environment-startup-tier0` | `PARTIAL` | Tier 0 environment, current SQLite/Alembic schema, legacy Settings migration, Windows startup, and API composition slices. | The exact-head follow-up passes fresh/warm official-launcher readiness, simulated provider-outage startup, changed-owner/PID-reuse protection, injected backend/frontend readiness-failure cleanup, canonical-state protection, and final port cleanup. The campaign is 23 `PASS`, 1 `PARTIAL`, 0 `BLOCKED`, and 44 `UNRUN`. | The safe historical before/after timing comparator remains unavailable; T0-04 stays partial for that timing limitation only. Downstream validation also remains partial or unrun. | — | 2026-09-25 | integration | [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [timing results](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/timing-results.md), [safety harness](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/launcher-safety-harness.json), [gate ledger](validation/gate_status.md) | Preserve the functional startup safety boundary; revisit timing only with a safe paired baseline. |
| `testing.complete-live-matrix` | `PARTIAL` | Complete live provider, browser, raster, composition, and coverage scenario matrix. | The controlled acknowledgement module passes 10/10; exact-lane browser evidence passes direct coordinates, 24-hour weather/AQ, ten pharmacy-filtered POIs, saved-history hydration, evidence inspection, and the complete 50-candidate discovery inventory. The current focused five-file suite passes 83 tests for this follow-up. | Explicit gaps remain for public raster loading, route aliases and semantics, provider parity, credentialed/local sources, dataset ingestion, and other catalog families. One live AQ run recovered from a semantic argument validation rejection; general Overpass reliability remains partial. | External providers and configured sources vary by environment; T0-04 timing remains partial. | 2026-09-25 | E2E + automated | [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [browser evidence](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md), [2026-09-25 continuation report](../QA/tier2-validation-develop-20260925-next-slices/report.md), [controlled module](../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/full-module.log) | Continue the remaining route, raster, provider, ingestion, recovery, and release rows with exact provider/model and browser-authoritative evidence. |
| `ci.hosted-exact-head` | `VALIDATED` | Hosted CI result for an exact pushed branch head. | Evidence commit `db5b9485e80073f87dd4a8b964e484ba42384fcb` passed all four jobs on [GitHub Actions run 36152093449](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36152093449); the implementation source exercised by this follow-up remained `800e0568f6b83254b60c4efe25e014e3fefdf81c`. The corrected implementation commit `952e92721f45a6bc245dc4ed6271c5e32a01017b` also passed all four jobs on [run 36116073402](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36116073402). | Live-browser status remains separately classified; the follow-up pushed head contains evidence and documentation only. | — | 2026-09-25 | hosted CI | [gate status](validation/gate_status.md), [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [hosted-CI evidence](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/hosted-ci-followup.md), [prior exact-head recheck report](../QA/tier2-validation-develop-20260924-head66008da/report.md) | Rerun hosted CI on future source or test changes. |
| `deployment.cross-platform` | `NOT_IMPLEMENTED` | First-class Docker deployment, Linux/macOS launcher, and standalone production distribution artifact. | Runtime modes explicitly list these capabilities as not implemented. | This is a product-scope boundary, not a failed local Windows workflow. | — | — | None | [runtime modes](runtime/modes.md), [deployment](runtime/deployment.md) | Implement only if cross-platform or standalone deployment becomes an approved scope. |

## Issues

This section retains current problems and resolved findings. Lifecycle status
and severity are independent of component status; an `UNVALIDATED` component is
not automatically an issue, and a `PARTIAL` component can have a low-severity
limitation.

### ISSUE-001 — Landmark and nearby-POI routing can use the wrong geography

- **Status:** RESOLVED (2026-09-23).
- **Affected component:** `agent.location-resolution.landmarks`; also
  `agent.capability-routing.live-language`.
- **Severity:** `HIGH`.
- **Description and impact:** The earlier Tehran/Iran candidate for an explicit
  Rome/Italy request and rejected POI executions prevented a safe landmark/nearby
  amenity claim.
- **Resolution:** Explicit country qualifiers are checked against the selected
  geocoder candidate's country and ISO code. POI map searches normalize their
  route to include both `MAP_RENDERING` and `DATA_RETRIEVAL`, even if the
  classifier omits secondary domains.
- **Evidence:** Current unit regressions reject Tehran/Iran for `central Rome,
  Italy`; exact-lane browser runs resolved the Colosseum and clarified central
  Rome to Italy, executed `overpass_poi_amenities`, rendered the layer, and
  received acknowledgement. See the [T2 retry report](../QA/tier2-validation-develop-20260923-retry/report.md)
  and [browser evidence](../QA/tier2-validation-develop-20260923-retry/browser-evidence.md).
- **Remaining limitation:** Overpass reports partial reliability and an
  approximately 2.5 km result extent. Broader keyless route coverage remains
  tracked under `ISSUE-006` and `ROUTE-LIVE`.
- **Remediation status:** Resolved and revalidated on `develop` 2026-09-23.
- **Related documentation:** [agentic search](geospatial/agentic_search.md),
  [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md),
  [T2 retry report](../QA/tier2-validation-develop-20260923-retry/report.md).

### ISSUE-002 — Public raster sources fail at the MapLibre load boundary

- **Affected component:** `maps.raster-overlays`, `maps.state-preservation`,
  and `agent.map-render-ack-recovery`.
- **Severity:** `HIGH`.
- **Description and impact:** FEMA retrieval now returns a usable raster
  descriptor, but the real browser cannot load/acknowledge the FEMA source.
  ESA WorldCover reached the renderer but also failed source loading. FEMA +
  USGS composition and retaining FEMA after gauge removal therefore remain
  blocked; no false raster success is allowed.
- **Evidence:** [2026-09-20 focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md)
  and [hazard/hydrology rerun](../QA/aegis-hazard-hydrology-e2e-20260920/report.md).
- **Suspected cause:** Not established. The observed failure boundary is the
  browser-side MapLibre source load after descriptor construction.
- **Blocker:** The unresolved public source/renderer boundary prevents a
  verified overlay and dependent composition tests.
- **Remediation status:** Open; provider retrieval and descriptor fixes are
  already retained as historical resolutions below.
- **Required revalidation:** FEMA, ESA WorldCover, and dependent composition /
  selective-removal rows must show visible source/layer state and
  `map.render_ack`.
- **Related documentation:** [provider framework](geospatial/providers/provider_framework.md),
  [gate ledger](validation/gate_status.md).

### ISSUE-005 — Controlled supersession acknowledgement ordering (resolved 2026-09-24)

- **Affected component:** `agent.map-render-ack-recovery`.
- **Severity:** `MEDIUM`.
- **Description and impact:** The previously reported supersession failure
  was not reproduced in the complete current controlled browser module. The
  superseded acknowledgement scenario and all other controlled cases pass.
- **Evidence:** The 2026-09-24 [full controlled module](../QA/tier2-validation-develop-20260924/controlled-fault/full-module.log)
  and the `CONTROLLED-FAULT` row in the [validation gate ledger](validation/gate_status.md).
- **Suspected cause:** No broader cause for the historical failure was
  confirmed.
- **Blocker:** None.
- **Remediation status:** Resolved 2026-09-24; the complete controlled module
  passed 10/10, including supersession, stale, mismatched, and retry-exhausted
  acknowledgements.
- **Required revalidation:** Keep the complete controlled module in the gate
  after changes to acknowledgement ordering or map recovery.
- **Related documentation:** [native harness](geospatial/native_harness_bootstrap.md),
  [gate ledger](validation/gate_status.md).

### ISSUE-006 — Several keyless capabilities remain unreachable or unreliable

- **Affected component:** `agent.capability-routing.live-language` and
  `providers.normalized-adapters`.
- **Severity:** `MEDIUM`.
- **Description and impact:** The latest keyless slice still recorded no
  supported route or incomplete execution for RainViewer, EEA noise, PVGIS
  solar, Census demographics, and some Open-Meteo aliases. This prevents a
  complete user-language capability claim even where catalog entries exist.
- **Evidence:** Capability rows `GEO-FOCUS-05`, `08`, `12`, `15`, and `16` in
  the [2026-09-20 focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md).
- **Suspected cause:** Causes vary by capability and are not collapsed into a
  single unverified root cause.
- **Blocker:** Some rows may also depend on upstream availability; keep those
  outcomes separate from route failures.
- **Remediation status:** Open.
- **Required revalidation:** For every affected capability, verify discovery,
  exact location, execution, provider result semantics, and browser rendering
  where a map is requested.
- **Related documentation:** [agentic search](geospatial/agentic_search.md),
  [provider framework](geospatial/providers/provider_framework.md),
  [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md).

## Resolved / historical findings

Resolved findings are retained only for provenance. They are not active issues
and must not be used to downgrade the current component status unless a
regression is observed.

| Finding | Previous failure | Current resolution evidence | Revalidate when |
| --- | --- | --- | --- |
| `HIST-001` `agent.route.bootstrap.plain-location` | Plain `Show me Springfield` could fail before place resolution. | Bounded server-owned fallback and a clean browser retest produced Springfield clarification and the correct Massachusetts map. | Agent routing or location bootstrap changes. |
| `HIST-002` `ui.basemap.preference` | A manually selected Dark basemap could be replaced by the default on the next location request. | Session-level manual preference and the ten-location browser retest preserved Dark. | Map-session or frontend state changes. |
| `HIST-003` `location.numeric-bounds` | Explicit out-of-range numeric coordinates could fall through to current context. | Typed bounds error and immediate Geneva recovery were observed; the existing map remained intact. | Location parsing or recovery changes. |
| `HIST-004` `maps.committed-state-narration` | Completion narration could trust a model claim instead of the committed visible overlay set. | FEMA/USGS removal retest reported the actual committed overlay state, not an unverified FEMA claim. | Finalization, map-state, or assistant narration changes. |
| `HIST-005` `providers.fema.arcgis-endpoint` | FEMA descriptor retrieval used an obsolete or unusable endpoint. | Current ArcGIS export descriptor retrieval now succeeds; browser source loading remains active `ISSUE-002`. | FEMA adapter, raster descriptor, or MapLibre source changes. |
| `HIST-006` `agent.data-bearing-map-policy` | Data-bearing map routes could be rejected by the map-only policy boundary. | WorldCover and Overpass route/policy fixes passed focused regression coverage and reached their correct provider/render boundaries. | Capability domains, policy, or route compilation changes. |
| `HIST-007` `quality.pyright-strict` | The repository strict gate reported 46 diagnostics and `PYRIGHT-STRICT` was `FAIL`. | T0-01 explicitly narrowed the invalid-coordinate branch, the full `app/server/pyproject.toml` run reports 0 errors, and the related regression file passes 9 tests. See the [T0-01 static-quality report](../QA/t0-01-static-quality-20260922/report.md). | Python typing, project configuration, or source changes. |
| `HIST-008` `ui.settings-provider-access.credential-lifecycle` | Controlled unreadable-credential and API-failure states were unverified; the exploratory model-card check used a stale selected-model context and did not wait for completion. | The [T1-10 report](../QA/tier1-validation-develop-20260923/T1-10/report.md) records passing masked save/clear, blank/invalid draft, unreadable-key, failed-update, and selected-model browser checks plus 38 backend and 33 Angular tests. A missing success-path UI refresh was repaired. | Settings credential display/save/clear behavior, selected-model response parsing, or model-selection UI changes. |
| `ISSUE-003` (closed 2026-09-23) `backend.api.sync-chat-turn` | Historical live timing evidence recorded 409 while a chat turn was running; a valid completed event also failed strict response hydration. | The [T1-06 report](../QA/tier1-validation-develop-20260923/T1-06/report.md) records live `200/202/409/404/503`, a genuine active-run conflict, 404 preflight with no run, safe 503 detail, and the terminal-hydration regression repair. | `/api/chat/turn`, run lifecycle, or terminal-event serialization changes. |

## Validation debt

Validation debt is a priority list for future testing, not a defect list. An
entry may remain `UNVALIDATED` or `BLOCKED` without implying that the feature is
broken.

| Component | Current confidence | Missing validation | Priority | Next validation action |
| --- | --- | --- | --- | --- |
| `runtime.startup.windows-local` | `PARTIAL` | Safe paired historical before/after timing comparator. | `HIGH` | Preserve the passing functional startup safety boundary; revisit timing only with a safe paired baseline. |
| `agent.capability-routing.live-language` | `PARTIAL` | Remaining route aliases and semantics, imagery extent, weather budget, and other live catalog families. | `HIGH` | Execute the remaining rows using the exact configured lane and browser-authoritative source/render evidence. |
| `agent.capability-discovery.inventory` | `VALIDATED` | No current gap in the bounded 50-candidate discovery-only slice. | — | Re-run after catalog pagination, runtime-budget, or discovery-route changes; keep provider and map-render boundaries separate. |
| `testing.complete-live-matrix` | `PARTIAL` | Full required provider, raster, composition, coverage, multilingual, and recovery rows. | `HIGH` | Execute the remaining rows with the exact configured lane and browser-authoritative evidence. |
| `model.provider-parity.openai-ollama` | `BLOCKED` | Provider-specific continuation and structured-output evidence. | `HIGH` | Supply the approved service/credential boundary and run each lane independently; never silently substitute. |
| `geospatial.dataset-ingestion` | `UNVALIDATED` | Representative materialization, checksum, source-health, and optional-format behavior. | `MEDIUM` | Run isolated dataset-ingestion validation and retain the report under `assets/QA/`. |
| `providers.credentialed-and-local-source-access` | `BLOCKED` | Approved credentialed provider runs and configured local snapshots/feeds. | `MEDIUM` | Configure only authorized sources, then run the provider smoke and relevant UI/map checks. |

## Update boundary

When evidence changes, update the smallest affected component row, issue, or
validation-debt entry. Keep active defects out of the resolved section, keep
validation debt separate from defects, and link to the detailed report that
establishes the conclusion. The invariant is:

> `project_status_ledger.md` represents the canonical current operational
> state; detailed architecture and validation documents explain the contracts
> and evidence used to establish that state.
