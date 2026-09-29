# Project Status Ledger

Last updated: 2026-09-29

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

The 2026-09-25 follow-up used the user-configured exact `opencode-go / deepseek-v4.1-flash` lane in a disposable isolated runtime. `T2-04` passes the complete 50-candidate discovery inventory after the approved temporary six-call budget was restored to four. `T0-04` is now `PASS`: its functional startup safety boundary is complete, and the unavailable historical timing comparator is explicitly non-gating. See the [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md) and [browser evidence](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md).

The 2026-09-26 Tier 3 follow-ups fixed named-landmark location-only recovery,
manual basemap warning cleanup, and temporal completion for current updates
that retain static overlays. They passed the current Colosseum, USGS gauge,
Census hydrography, vector-composition, selective-removal, layer-visibility,
Dark, and OpenTopoMap browser slices. The 2026-09-28 NOAA continuation now
resolves official affected-zone boundaries for null-geometry alerts and passes
the exact-lane browser render/acknowledgement boundary. The fresh exact-lane
raster continuation on `develop@be61298` revalidated attributed FEMA and ESA
retrievals plus their real MapLibre source/layer failures; the matching
acknowledgements failed and no raster pixels were obtained. A follow-up
request-level Playwright capture now shows FEMA requests failing with
`ERR_CONNECTION_RESET` and ESA requests failing with
`ERR_HTTP2_PROTOCOL_ERROR`, with no response events or HTTP statuses. This
establishes a browser/network transport boundary but not a repository-owned
URL or renderer defect. USGS rendered by itself, but FEMA
composition/retention remain blocked. The 2026-09-29 implementation follow-up
now routes FEMA, ESA WorldCover, and GIBS browser raster descriptors through the
manifest-backed AEGIS tile proxy, with local transport contracts and quality
checks passing. Its exact-lane live preflight reported an empty provider/model
and failed before any raster request, so no browser pixels or acknowledgement
claim was added. The remaining Tier 3 slices are still unrun.
See the [NOAA remediation report](../QA/tier3-validation-develop-20260928-noaa/report.md),
[map rendering report](../QA/tier3-validation-develop-20260926-map-rendering/report.md),
and [vector-composition report](../QA/tier3-validation-develop-20260926-vector-composition/report.md).

**Current project posture: `PARTIAL`.** The native runtime and core browser
interaction paths have meaningful local and manual proof. The complete live
geospatial matrix, several public-provider routes, live raster rendering,
and some optional integrations remain incomplete or unvalidated. Exact-head hosted CI passed for the T1-09 implementation and the raster evidence
commit `51f94d2bc82e8510df1b70730b3b722ca272b64e` (four of four jobs). The
subsequent ledger-only reconciliation records that exact workflow target; each
later implementation or evidence push still requires its own hosted result.

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
| `runtime.startup.windows-local` | `VALIDATED` | Windows launcher port-consent guard, warm dependency/build reuse, concurrent backend/frontend startup, isolated no-op database startup, and fail-closed cleanup. | The exact-head follow-up records four successful official-launcher starts in the isolated runtime; the simulated provider-outage startup test, changed-owner/PID-reuse protection, injected backend/frontend readiness-failure cleanup, canonical-state protection, and final port cleanup all pass. Angular `ng serve` still compiles at launch. | No safe same-machine historical before/after timing comparator exists, so no performance delta is claimed; this unavailable comparator is not a product or validation defect. | — | 2026-09-28 | E2E + automated | [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [timing results](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/timing-results.md), [safety harness](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/launcher-safety-harness.json), [startup](runtime/startup.md) | Preserve the functional startup safety boundary; do not reopen timing without a meaningful paired baseline. |
| `catalog.manifests-and-auditor` | `VALIDATED` | Runtime catalog loading and strict production manifest audit. | The 2026-09-28 strict production audit after the PVGIS runtime-profile change records 86 manifests, 0 errors, and 0 warnings. | Catalog coverage is not the same as live-provider or browser-render proof. | — | 2026-09-28 | integration | [environmental follow-up](../QA/tier3-validation-develop-20260928-environmental/report.md), [quality checks](../QA/tier3-validation-develop-20260928-environmental/quality-checks.log), [manifest contract](geospatial/manifests/manifest_contract.md), [ingestion validation](geospatial/ingestion/validation.md) | Re-run the strict production auditor after manifest or runtime-profile changes. |
| `backend.agent.native-loop` | `VALIDATED` | Native route, typed tool exposure, observation/recovery cycle, bounded context, and terminal completion contracts. | The 2026-09-25 regression passed 115 focused tests and the full 420-test backend CI selection locally; strict Pyright reports 0 errors/warnings/informations. The selected exact lane completed coordinate, direct forecast, saved-evidence inspection, and map-handoff scenarios. Exact-source hosted CI run `36116073402` passed all four jobs after fixing strict typing and regenerating the shared OpenAPI enum. | Live provider and full-browser scenario coverage remain separate; one live AQ run recovered from a model-generated semantic argument rejection. | - | 2026-09-25 | integration/E2E | [2026-09-25 report](../QA/tier2-validation-develop-20260925-next-slices/report.md), [browser evidence](../QA/tier2-validation-develop-20260925-next-slices/browser-evidence.md), [native harness](geospatial/native_harness_bootstrap.md), [gate ledger](validation/gate_status.md), [2026-09-24 focused report](../QA/tier2-validation-develop-20260924-head77c5d67/report.md) | Re-run the focused native suite after agent-loop, route, policy, or tool changes; rerun hosted CI on future source or test changes. |
| `backend.run-lifecycle-and-persistence` | `VALIDATED` | SQLite migrations, revisioned conversation state, durable run events, terminal finalization, and last-known-good presentation preservation. | Migration and terminal-presentation gates are passing in the detailed validation ledger. | No current defect is evidenced in the tested local scope. | — | 2026-09-17 | integration | [persistence](architecture/persistence.md), [native harness](geospatial/native_harness_bootstrap.md), [gate ledger](validation/gate_status.md) | Re-run isolated Alembic and run-lifecycle tests after schema or persistence changes. |
| `backend.api.sync-chat-turn` | `VALIDATED` | Synchronous chat-turn response boundary and orchestration behavior. | The [T1-06 report](../QA/tier1-validation-develop-20260923/T1-06/report.md) records the exact-lane live `200/202/409/404/503` matrix, 14 focused API/OpenAPI tests, and 397 corrected backend CI tests. | No current T1-06 defect is evidenced; completed-event hydration now removes run-only state and restores omitted nullable context usage before response validation. | — | 2026-09-23 | integration | [T1-06 report](../QA/tier1-validation-develop-20260923/T1-06/report.md), [backend API](architecture/backend_api.md), [gate status](validation/gate_status.md) | Preserve status distinctions and safe error detail when the chat route or run lifecycle changes. |
| `model.opencode-go.deepseek-v4.1-flash` | `VALIDATED` | Exact configured provider/model lane readiness and visible selection without silent fallback. | The 2026-09-28 investigation reproduced the 401 from a stale credential stored in the canonical database, moved the healthy database to `data/database.db`, saved the supplied credential through `PATCH /api/chat/settings`, loaded 30 live OpenCode Go models, and completed the native structured probe with `parse_status=complete`. | No current provider-readiness defect is evidenced. No fallback or provider switch was used. | — | 2026-09-28 | E2E | [exact readiness report](../QA/tier3-validation-develop-20260928-raster/opencode-go-readiness-report.md), [credential-path check](../QA/tier3-validation-develop-20260928-raster/credential-path-check.json), [gate ledger](validation/gate_status.md) | Preserve the exact provider/model and re-run this gate after credential or data-root changes; keep live MapLibre source/layer acknowledgement separate. |
| `model.provider-parity.openai-ollama` | `BLOCKED` | Provider-specific continuation and structured-output proof outside the exercised OpenCode Go lane. | Native implementation documents say OpenAI Responses and Ollama remain unrun; the live boundary retains Ollama-unavailable behavior rather than falling back. | No current parity claim is allowed. | Required provider credentials/services were not available for the recorded validation boundary. | — | None | [native harness](geospatial/native_harness_bootstrap.md), [configuration](runtime/configuration.md), [gate ledger](validation/gate_status.md) | Run provider-specific continuation probes when each service and approved credential is available. |
| `agent.capability-routing.live-language` | `PARTIAL` | Natural-language routing and capability discovery for keyless geospatial requests. | The 2026-09-25 focused five-file regression passes 83 tests in this follow-up, while the 2026-09-26 route regression adds the cleared-secondary-domain location-only normalization. The exact lane now passes current Colosseum recovery, USGS gauge routing, and the NOAA alert route. The 2026-09-28 GEO-FOCUS-16 follow-up also passes PVGIS Rome discovery, direct-text normalization, provider execution, and numeric result narration; EEA Milan discovery and provider execution pass before the raster render boundary. | `ISSUE-006` and remaining gaps: RainViewer, Census demographics, Open-Meteo aliases, Acropolis semantics, imagery extent, weather budget, generic-infrastructure clarification, and broader route-family coverage. EEA source loading and map-recovery behavior remain `PARTIAL`; Overpass reports partial reliability and bounded coverage. | — | 2026-09-28 | E2E + automated | [environmental follow-up](../QA/tier3-validation-develop-20260928-environmental/report.md), [environmental browser evidence](../QA/tier3-validation-develop-20260928-environmental/browser-evidence.md), [Tier 3 report](../QA/tier3-validation-develop-20260926-map-rendering/report.md), [NOAA remediation report](../QA/tier3-validation-develop-20260928-noaa/report.md), [browser evidence](../QA/tier3-validation-develop-20260926-map-rendering/browser-evidence.md), [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [focused suite](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/focused-suite.log) | Preserve the location-only and metadata-only recovery boundaries and continue the remaining route matrix with exact source, coverage, and render evidence. |
| `agent.capability-discovery.inventory` | `VALIDATED` | Bounded runtime catalog pagination, result semantics, and discovery-only completion without map rendering. | The exact-lane browser run completed five successful pages (`12+12+12+12+2`) for 50 candidates, 50 unique IDs, and final `next_cursor=null`; the map session remained empty and six model calls stayed within the approved isolated `max_model_calls=6` budget. The setting was restored to `4` after restart. | This proves the bounded inventory slice only; it does not validate every provider, route family, renderer, credentialed source, or raster layer. | — | 2026-09-25 | E2E + automated | [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [browser evidence](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md), [run trace](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/inventory-run-trace.json), [focused suite](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/focused-suite.log) | Re-run after catalog pagination, runtime-budget, or discovery-route changes; keep provider and map-render boundaries separate. |
| `agent.location-resolution.core` | `VALIDATED` | Direct locations, clarification, invalid-coordinate bounds, safe recovery, and repeated location changes. | Exact-lane browser evidence passes Florence clarification while retaining Rome, canonical Milan/Texas ambiguity labels, and explicit Milan, Italy rendering. Prior Zurich bounds rejection and Springfield clarification remain linked evidence. | Other language and geography combinations remain part of the broader partial route matrix. | — | 2026-09-24 | E2E | [current browser evidence](../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [prior core report](../QA/core-behavior-e2e-20260919/final-report.md), [agentic search](geospatial/agentic_search.md) | Preserve clarification-before-replacement and canonical locality/region/country labels; broaden only through the exact-lane matrix. |
| `agent.location-resolution.landmarks` | `VALIDATED` | Landmark-centric location resolution and nearby-amenity routing. | Current T2-03 browser runs resolved the Colosseum and clarified central Rome to the correct Italy location, discovered `overpass_poi_amenities`, rendered the layer, and received browser acknowledgement. | Overpass reports partial reliability and roughly 2.5 km coverage; the broad keyless capability matrix remains `PARTIAL`. | — | 2026-09-23 | E2E | [T2 retry report](../QA/tier2-validation-develop-20260923-retry/report.md), [browser evidence](../QA/tier2-validation-develop-20260923-retry/browser-evidence.md), [agentic search](geospatial/agentic_search.md) | Expand to the remaining landmark and POI catalog routes without promoting provider-reported counts to independent ground truth. |
| `agent.map-render-ack-recovery` | `PARTIAL` | Candidate map preparation, browser acknowledgement, failed-render recovery, supersession, and last-known-good preservation. | Current exact-lane Colosseum recovery, NOAA/USGS/Census render acknowledgement, vector composition/removal, and controlled recovery evidence remain scoped PASS. The GEO-FOCUS-16 EEA run reached provider execution and prepared a candidate, but the public raster source failed at MapLibre and subsequent recovery calls were schema/semantic-invalid; the last-known-good map preservation message remained visible. The fresh `develop@be61298` FEMA and ESA runs likewise failed before accepted acknowledgement. | `ISSUE-002`: public raster source failures remain unresolved; the latest EEA/FEMA/ESA evidence confirms provider retrieval can succeed while browser source loading fails, without confirming a repository-owned URL or renderer defect. | FEMA/EEA source/layer acknowledgement remains the prerequisite for raster-dependent composition and recovery claims. | 2026-09-28 | E2E | [environmental follow-up](../QA/tier3-validation-develop-20260928-environmental/report.md), [environmental browser evidence](../QA/tier3-validation-develop-20260928-environmental/browser-evidence.md), [map-rendering report](../QA/tier3-validation-develop-20260926-map-rendering/report.md), [NOAA remediation report](../QA/tier3-validation-develop-20260928-noaa/report.md), [raster remediation report](../QA/tier3-validation-develop-20260928-raster-remediation/report.md), [request diagnostics](../QA/tier3-validation-develop-20260928-raster-diagnostics/report.md), [controlled module](../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/full-module.log) | Preserve fail-closed acknowledgement behavior; retry in a network-capable browser and change code only if a repository-owned defect is reproduced. |

### Geospatial data, maps, and integrations

| Component | Status | Scope | Evidence | Known Issues | Blocker | Last Validated | Validation Level | Related Docs | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `providers.normalized-adapters` | `PARTIAL` | Provider registry, normalized feature/raster/metadata responses, attribution, stale/empty/error semantics, and selected live adapters. | The 2026-09-25 live run verified a pharmacy-only Overpass query with ten `pharmacy` records, `ok`/not-stale/not-truncated evidence, and visible OSM attribution; the exact lane also returned 24-row Open-Meteo weather and air-quality windows. The 2026-09-26 browser run additionally verified Census hydrography and USGS water-gauge composition with visible provider attributions. The 2026-09-28 GEO-FOCUS-16 follow-up now verifies PVGIS `metadata` normalization with a numeric annual estimate and EEA `raster` retrieval with attribution; EEA source loading still fails in MapLibre. | FEMA/ESA/EEA retrieval works but their public raster sources do not load in MapLibre; GIBS was upstream-unavailable; broader Census/USGS/catalog coverage remains incomplete. The Overpass provider continues to advertise partial general reliability. | — | 2026-09-28 | E2E + automated | [environmental follow-up](../QA/tier3-validation-develop-20260928-environmental/report.md), [live raster report](../QA/tier3-validation-develop-20260928-raster-live/report.md), [vector-composition report](../QA/tier3-validation-develop-20260926-vector-composition/report.md), [provider framework](geospatial/providers/provider_framework.md) | Investigate the public raster source-load boundary, then run the broader provider smoke matrix while preserving distinct upstream, routing, credential, and renderer outcomes. |
| `maps.basemap-switching` | `VALIDATED` | Supported basemap rendering, switching, manual preference preservation, and return to a stable map. | Core browser report verified supported basemap switches and Dark-basemap persistence across ten location changes. The 2026-09-26 live run additionally rendered Dark Basemap and OpenTopoMap Terrain over the current USGS map and confirmed a successful manual recovery clears the prior warning. | Reload/new-chat reset to the documented catalog default by design; this does not prove every public raster source. | — | 2026-09-26 | E2E | [Tier 3 report](../QA/tier3-validation-develop-20260926-map-rendering/report.md), [browser evidence](../QA/tier3-validation-develop-20260926-map-rendering/browser-evidence.md), [frontend architecture](architecture/frontend_architecture.md), [state preservation](ui/state_preservation.md) | Re-run the switch/persistence flow after renderer or session-state changes and keep source-specific failures separate. |
| `maps.vector-overlays` | `VALIDATED` | Demonstrated GeoJSON/point/line/polygon overlay rendering and visible attribution for selected public paths. | The 2026-09-26 exact-lane run retrieved 48 USGS gauges, rendered the clustered point layer with USGS attribution, exercised hide/show visibility (`1/1` → `0/1` → `1/1`), rendered 13 Census hydrography features, composed both public vector layers (`2/2`, 13 + 2 rendered), and selectively removed USGS while retaining Census. The 2026-09-28 exact-lane NOAA request rendered the affected-zone `GeometryCollection` with NOAA attribution. Residential buildings, earthquakes, coastal stations, atmospheric points, and historical NOAA valid-empty behavior remain additional selected paths. | This is a demonstrated subset, not proof of the complete catalog; other vector families and NOAA valid-empty behavior remain unrun. | — | 2026-09-28 | E2E | [map-rendering report](../QA/tier3-validation-develop-20260926-map-rendering/report.md), [NOAA remediation report](../QA/tier3-validation-develop-20260928-noaa/report.md), [vector-composition report](../QA/tier3-validation-develop-20260926-vector-composition/report.md), [vector browser evidence](../QA/tier3-validation-develop-20260926-vector-composition/browser-evidence.md), [frontend architecture](architecture/frontend_architecture.md), [geospatial validation](geospatial/ingestion/validation.md) | Expand the matrix while keeping visible source/layer and acknowledgement evidence for every map claim. |
| `maps.raster-overlays` | `PARTIAL` | Raster, WMS, and WMTS descriptor execution through the real MapLibre renderer. | The manifest-backed AEGIS tile proxy, native map-plan proxy descriptor, FEMA ArcGIS bbox materialization, ESA WMTS construction, GIBS WMTS/WMS selection, focused tests, and strict audit pass. The exact `opencode-go / deepseek-v4.1-flash` probe passed on 2026-09-29; FEMA/ESA browser traffic used the AEGIS proxy with zero direct-upstream requests, but provider tile requests returned `502` before MapLibre source/layer acknowledgement. | `ISSUE-002`: no successful EEA, FEMA, WorldCover, or GIBS pixels, visible source/layer completion, or accepted `map.render_ack`; the prior direct-provider renderer exposure was repaired in the native map-plan path, while public upstream availability remains unresolved. | Need a successful provider image response plus actual rendered public raster source/layer state with matching run/session/revision acknowledgement before promotion. | 2026-09-29 | E2E + automated | [2026-09-29 T3-07/T3-08 report](../QA/tier3-validation-develop-20260929-t3-07-t3-08/report.md), [browser evidence](../QA/tier3-validation-develop-20260929-t3-07-t3-08/browser-evidence.md), [network summary](../QA/tier3-validation-develop-20260929-t3-07-t3-08/network-summary.json), [quality results](../QA/tier3-validation-develop-20260929-t3-07-t3-08/quality-checks.log), [prior raster remediation](../QA/tier3-validation-develop-20260928-raster-remediation/report.md) | Re-run with a network-capable exact lane and request-level status; promote only after successful image transport and browser-authoritative acknowledgement. |
| `maps.state-preservation` | `PARTIAL` | Overlay removal, visible-state narration, basemap preference, composition, and retaining an existing overlay during changes. | Existing Census/USGS composition and selective removal remain supported by prior evidence. The fresh exact-lane run rendered USGS alone after FEMA failed; the subsequent gauge-removal run acknowledged an attributed basemap with zero overlays. It did not retain FEMA because FEMA had never rendered. [raster remediation report](../QA/tier3-validation-develop-20260928-raster-remediation/report.md), [browser observations](../QA/tier3-validation-develop-20260928-raster-remediation/browser-evidence.md), [run summary](../QA/tier3-validation-develop-20260928-raster-remediation/run-summary.json) | `ISSUE-002`: FEMA-specific composition and retention remain unproven; the empty overlay state after removal is not a FEMA retention pass. | A visible, acknowledged FEMA overlay is required before GEO-HYD-05/GEO-HYD-06 can complete. | 2026-09-28 | E2E | [raster remediation report](../QA/tier3-validation-develop-20260928-raster-remediation/report.md), [browser observations](../QA/tier3-validation-develop-20260928-raster-remediation/browser-evidence.md), [run summary](../QA/tier3-validation-develop-20260928-raster-remediation/run-summary.json), [vector-composition report](../QA/tier3-validation-develop-20260926-vector-composition/report.md), [state preservation](ui/state_preservation.md) | Continue composition/removal across rendered overlays; rerun FEMA retention only after its source/layer acknowledgement passes. |
| `providers.credentialed-and-local-source-access` | `BLOCKED` | Credentialed providers and configured local feeds or snapshots such as OpenAQ, TomTom, OpenTripMap, Windy, Google Maps, ArcGIS, NASA FIRMS, GTFS, Overture, Open Charge Map, and local cameras. | Recent live reports explicitly excluded these paths because required credentials, snapshots, feeds, or local datasets were absent. | Absence in this environment is not an application defect. | Approved credentials and/or configured local source artifacts are unavailable. | — | None | [access overview](geospatial/providers/access_overview.md), [provider sources](geospatial/providers/public_and_optional_sources.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Configure only approved sources, then run the dedicated provider and browser checks without exposing secrets. |
| `geospatial.dataset-ingestion` | `UNVALIDATED` | Dataset-ingestion manifests, CSV/GeoJSON materialization, checksums, source health, and optional heavy-format handling. | Contracts and validation workflow are documented; no recent convincing end-to-end ingestion run is recorded in the current QA set. | Heavy GIS formats are intentionally optional and may remain partial. | — | — | None | [dataset ingestion](geospatial/ingestion/dataset_ingestion.md), [ingestion validation](geospatial/ingestion/validation.md) | Run a representative isolated ingestion workflow and record its artifact and source-health evidence. |

### UI, quality, delivery, and coverage

| Component | Status | Scope | Evidence | Known Issues | Blocker | Last Validated | Validation Level | Related Docs | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ui.chat-map-workspace` | `VALIDATED` | Startup-to-chat flow, clarification, map controls, transcript hygiene, recovery, and repeated core location use. | Current exact-lane evidence shows Rome transcript/map, Florence clarification before replacement with visible acknowledgement, and canonical Milan choices followed by an attributed, acknowledged Italy map. DSML protocol-looking finalizer content remains suppressed. | Broad route families, source/raster behavior, and complete provider/browser coverage remain separate partial gates. | — | 2026-09-24 | E2E | [frontend architecture](architecture/frontend_architecture.md), [core report](../QA/core-behavior-e2e-20260919/final-report.md), [current T2 report](../QA/tier2-validation-develop-20260924-head77c5d67/report.md), [browser evidence](../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md) | Keep location clarification, visible `map.render_ack`, attribution, and transcript hygiene in the browser smoke. |
| `ui.settings-provider-access` | `VALIDATED` | Settings sections for model selection, model-provider credentials, local runtime, geospatial access, and persisted application runtime configuration. | T1-09 navigation/drafts and T1-10 credential lifecycle both pass. T1-10 validates masked state, safe model/geospatial save and clear, blank/invalid drafts, unreadable credentials, API failures, and the targeted selected-model response. See the [T1-10 report](../QA/tier1-validation-develop-20260923/T1-10/report.md). | Live provider authentication/connectivity remains outside this UI gate and is tracked separately as blocked provider access/parity. | — | 2026-09-23 | integration/E2E | [frontend architecture](architecture/frontend_architecture.md), [access overview](geospatial/providers/access_overview.md), [user settings](user/settings_and_access.md), [runtime validation](../QA/settings-runtime-validation-20260921.md), [T1-09 report](../QA/tier1-validation-develop-20260923/T1-09/report.md), [T1-10 report](../QA/tier1-validation-develop-20260923/T1-10/report.md) | Continue campaign at T2-01; rerun the Settings flow after credential UI or API contract changes. |
| `validation.application-foundations-tier1` | `VALIDATED` | Tier 1 route, state, conversation, realtime, run, API, jobs, Settings, credential, model, and context foundations. | T1-10 passed on `develop@8e32f82e3f094e5fb17c3978fad69b9f80b7af0b`; Tier 1 remains 12 `PASS`. The current campaign roll-up is 30 `PASS` / 1 `PARTIAL` / 0 `BLOCKED` / 37 `UNRUN` after reclassifying the unavailable T0-04 timing comparator as non-gating, validating the raster descriptor boundary, closing T3-04, and opening the live T3-07 raster boundary. | Broader downstream live/browser/provider coverage remains open; the exact provider lane and real public raster source-load boundary are separately classified. | - | 2026-09-28 | integration/E2E | [validation strategy](validation/strategy.md), [NOAA T3-04 report](../QA/tier3-validation-develop-20260928-noaa/report.md), [live raster report](../QA/tier3-validation-develop-20260928-raster-live/report.md), [Tier 1 checklist](validation/tier1_application_foundations.md) | Complete the remaining partial and unrun slices while keeping browser, provider, and exact-head CI boundaries distinct. |
| `quality.pyright-strict` | `VALIDATED` | Strict repository-wide Python typing gate. | The current Tier 0 sweep reports 0 errors, 0 warnings, and 0 informations under `app/server/pyproject.toml`; Python source compilation also passed for 410 files. | — | — | 2026-09-22 | integration | [Tier 0 final report](../QA/tier0-validation-develop-20260922/final/report.md), [testing and quality](coding/testing_and_quality.md), [gate ledger](validation/gate_status.md) | Rerun the full strict project configuration after typing or project-configuration changes. |
| `quality.ruff-and-frontend-regressions` | `VALIDATED` | Repository-wide Ruff, Angular production build, frontend state helper, and Karma regression suite. | The current Tier 0 sweep passes Ruff, 19 frontend-state tests, the Angular production build, and 248/248 Karma tests. | Existing frontend sanitizer/deprecation diagnostics remain non-failing warnings. | — | 2026-09-22 | integration | [Tier 0 final report](../QA/tier0-validation-develop-20260922/final/report.md), [testing and quality](coding/testing_and_quality.md), [gate ledger](validation/gate_status.md) | Rerun the relevant frontend suite when frontend or shared contract files change. |
| `validation.environment-startup-tier0` | `VALIDATED` | Tier 0 environment, current SQLite/Alembic schema, legacy Settings migration, Windows startup, and API composition slices. | The exact-head follow-up passes fresh/warm official-launcher readiness, simulated provider-outage startup, changed-owner/PID-reuse protection, injected backend/frontend readiness-failure cleanup, canonical-state protection, and final port cleanup. The unavailable historical timing comparator is recorded as non-gating rather than a partial product result. | Downstream validation remains partial or unrun; no Tier 0 defect is evidenced. | — | 2026-09-28 | integration | [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [2026-09-28 raster report](../QA/tier3-validation-develop-20260928-raster/report.md), [timing results](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/timing-results.md), [safety harness](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/launcher-safety-harness.json), [gate ledger](validation/gate_status.md) | Preserve the functional startup safety boundary and continue the remaining downstream slices. |
| `testing.complete-live-matrix` | `PARTIAL` | Complete live provider, browser, raster, composition, and coverage scenario matrix. | The controlled acknowledgement module and scoped location, NOAA, USGS/Census vector, composition/removal, visibility, basemap, exact provider readiness, and GEO-FOCUS-16 environmental evidence remain valid. The PVGIS direct-text route now passes end to end; EEA provider retrieval passes but its public raster source does not load in MapLibre. The 2026-09-29 raster proxy repair and local contracts pass; FEMA/ESA reached proxy transport but public tiles returned `502`, while all 12 GIBS prompts hit the assistant execution limit before raster routing. | Public raster source loading, remaining route aliases and semantics, provider parity, credentialed/local sources, dataset ingestion, broad recovery, and remaining Tier 3–5 rows remain incomplete. | T3-07 is PARTIAL; T3-08 is UNRUN; GEO-HYD-05/06 are blocked until a visible FEMA render; GEO-FOCUS-16 is PARTIAL on EEA render; MATRIX-22 remains partial. | 2026-09-29 | E2E + automated | [2026-09-29 T3-07/T3-08 report](../QA/tier3-validation-develop-20260929-t3-07-t3-08/report.md), [browser evidence](../QA/tier3-validation-develop-20260929-t3-07-t3-08/browser-evidence.md), [environmental follow-up](../QA/tier3-validation-develop-20260928-environmental/report.md), [raster remediation report](../QA/tier3-validation-develop-20260928-raster-remediation/report.md), [request diagnostics](../QA/tier3-validation-develop-20260928-raster-diagnostics/report.md), [controlled module](../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/full-module.log) | Continue the remaining route, raster, provider-parity, ingestion, recovery, and release rows with the exact provider/model and browser-authoritative evidence. |
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
  ESA WorldCover also returned an attributed renderable descriptor, but both
  public rasters failed the MapLibre source/layer checks. FEMA + USGS
  composition and retaining FEMA after gauge removal therefore remain blocked;
  no false raster success is allowed.
- **Evidence:** [2026-09-20 focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md),
  [hazard/hydrology rerun](../QA/aegis-hazard-hydrology-e2e-20260920/report.md),
  [descriptor boundary report](../QA/tier3-validation-develop-20260928-raster/report.md),
  the [fresh live raster report](../QA/tier3-validation-develop-20260928-raster-live/report.md), the [2026-09-28 remediation report](../QA/tier3-validation-develop-20260928-raster-remediation/report.md), and the [request-level diagnostics](../QA/tier3-validation-develop-20260928-raster-diagnostics/report.md) with [browser evidence](../QA/tier3-validation-develop-20260928-raster-diagnostics/browser-evidence.md).
- **Suspected cause:** One implementation defect is confirmed and fixed:
  direct layer-feature requests did not forward catalog metadata to descriptor
  providers, producing an incomplete ESA WMTS descriptor. The exact provider
  probe and descriptor regressions pass. The new request-level capture shows
  FEMA requests failing with `ERR_CONNECTION_RESET` and ESA requests failing
  with `ERR_HTTP2_PROTOCOL_ERROR`, with no response events or HTTP statuses.
  This places the latest failure before the image response, but does not prove
  whether the upstream service or the current browser/network path is at
  fault. Authentication is not the current blocker.
- **Blocker:** The unresolved public source/renderer boundary prevents a
  verified overlay and dependent composition tests. The diagnostic run made no
  speculative renderer change; a network-capable browser or successful image
  response is still required before assigning a repository defect.
- **Remediation status:** Open; the descriptor propagation repair, exact
  provider readiness, and reusable request-level diagnostic are validated,
  while the fresh FEMA/ESA runs still fail before a response and dependent
  composition/retention remains blocked.
- **Required revalidation:** After the public source failure is repaired, FEMA,
  ESA WorldCover, and dependent composition/selective-removal rows must show
  visible source/layer state and `map.render_ack`; retain the request-level
  diagnostic capture for any future failure.
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
- **Description and impact:** The 2026-09-28 environmental follow-up closes
  the PVGIS routing and normalized-result boundary: the exact lane now returns
  a numeric metadata-only solar estimate for Rome. EEA noise now reaches
  provider retrieval and returns an attributed renderable raster descriptor,
  but its public source still fails at the MapLibre load boundary. RainViewer,
  Census demographics, and some Open-Meteo aliases remain unvalidated or
  incomplete, so the complete user-language capability claim remains open.
- **Evidence:** [GEO-FOCUS-16 environmental follow-up](../QA/tier3-validation-develop-20260928-environmental/report.md), plus capability rows `GEO-FOCUS-05`, `08`, `12`, and `15` in the [2026-09-20 focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md).
- **Suspected cause:** Causes vary by capability and are not collapsed into a
  single unverified root cause.
- **Blocker:** Some rows may also depend on upstream availability; keep those
  outcomes separate from route failures.
- **Remediation status:** Partially remediated 2026-09-28; PVGIS is now
  `PASS`, EEA is `PARTIAL` at browser raster loading, and the remaining
  capabilities stay open.
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
| `ci.hosted-exact-head` | `VALIDATED` | Hosted CI result for an exact pushed branch head. | GitHub Actions push run 36447036544 completed successfully with all four jobs green for exact evidence commit `develop@51f94d2bc82e8510df1b70730b3b722ca272b64e`. The tested application source was `develop@be61298ddf4ae1c0b6900810b046c10d97e4993a`; the final gate ledger update is docs-only and is not the workflow target. | Hosted CI is tied to the recorded evidence SHA and does not substitute for live-provider/render evidence. | — | 2026-09-28 | hosted CI | [gate status](validation/gate_status.md), [raster remediation report](../QA/tier3-validation-develop-20260928-raster-remediation/report.md), [hosted workflow result](../QA/tier3-validation-develop-20260928-raster-remediation/hosted-ci.json), [GitHub Actions run 36447036544](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36447036544) | Recheck hosted CI on the exact SHA after the next implementation or evidence push; keep the source SHA and workflow conclusion paired. |
