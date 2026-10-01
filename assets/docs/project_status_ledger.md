# Project Status Ledger

Last updated: 2026-10-01

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
established a browser/network transport boundary but not a repository-owned
URL or renderer defect. USGS rendered by itself, but FEMA
composition/retention remained blocked. The 2026-09-29 implementation follow-up
routes FEMA, ESA WorldCover, and GIBS browser raster descriptors through the
manifest-backed AEGIS tile proxy, with local transport contracts and quality
checks passing. The 2026-10-01 T3-07 follow-up resolves the FEMA transport
blocker: `hazards.fema.gov` is US-egress-restricted (TLS reset from non-US
networks), and FEMA now reaches it through FEMA's official ArcGIS Online relay
with the required `Origin`/`Referer` headers. FEMA and ESA public raster
overlays now load through the same-origin AEGIS tile proxy and render with
accepted `map.render_ack`; the FEMA overlay is presented at a visible zoom and
raster results satisfy the `spatial_scope_applied` requirement. The 2026-09-29 exact-lane live preflight had reported an empty provider/model
and failed before any raster request, so no browser pixels or acknowledgement
claim was added then. The 2026-10-01 route-matrix continuation runs the
`ISSUE-006`/`ROUTE-LIVE` rows and the EEA render retry: Acropolis, Open-Meteo
aliases, generic-infrastructure clarification, and the weather-forecast row
(all at an adequate runtime budget) pass; census demographics, numeric
elevation, and imagery extent remain `PARTIAL`; EEA is now routed through the
same-origin AEGIS tile proxy but its render stays blocked by the retired
`noise.discomap.eea.europa.eu` 2019 WMS. See the
[route-matrix report](../QA/tier3-validation-develop-20261001-route-matrix/report.md).
The remaining Tier 3 slices are still unrun.
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

The 2026-09-30 native reliability implementation remains **PARTIAL** overall.
Google multi-step native continuation, task-aware evidence checks, deterministic
catalog pagination, private protocol projection, and hot execution settings with
checkpoint snapshots pass local regression checks. The full backend suite passed
1,025 tests; the final focused suite passed 366, and the focused client suite
passed 71. The Settings save/default restoration flow was inspected in the
in-app browser. Required raster visibility is fail-closed when unknown. The
current-head P0 raster contract passes controlled opaque/transparent,
transport, zoom, temporal, and recovery cases, while a real browser
pixel-proof producer, accepted `map.render_ack`, and complete recovery matrix
remain open. No fresh live model parity or A–E performance comparison was run.
This does not promote MATRIX-22 or existing provider/raster gates. See the
[implementation report](../QA/native-reliability-report-20260930.md) and the
[Tier 3 current-head follow-up](../QA/tier3-remediation-20260930/current-head-followup-889066b3.md).

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
| `agent.capability-routing.live-language` | `PARTIAL` | Natural-language routing and capability discovery for keyless geospatial requests. | The 2026-09-25 focused five-file regression passes 83 tests in this follow-up, while the 2026-09-26 route regression adds the cleared-secondary-domain location-only normalization. The exact lane now passes current Colosseum recovery, USGS gauge routing, and the NOAA alert route. The 2026-09-28 GEO-FOCUS-16 follow-up also passes PVGIS Rome discovery, direct-text normalization, provider execution, and numeric result narration; EEA Milan discovery and provider execution pass before the raster render boundary. The 2026-09-30 RainViewer request reaches capability execution, the exact Settings-API/model bootstrap, and browser-visible raster acknowledgement in the disposable runtime. The 2026-10-01 route-matrix continuation passes Acropolis semantics (correct Athens render + ack), Open-Meteo air/weather aliases, generic-infrastructure clarification, and the weather-forecast row once the runtime budget is adequate (default `simple_max_model_calls=4` is too tight for the exact-lane forecast flow, a configuration value); Census demographics and numeric elevation are unreachable because their capabilities are `defaultEnabled:false` manual-toggle; imagery extent fails backend render-scope validation. | `ISSUE-006` and remaining gaps: Census demographics / numeric elevation / imagery extent remain `PARTIAL` (manual-toggle and model/tool-call boundaries), and broader route-family coverage stays open. The weather forecast is `PASS` at an adequate runtime budget; the default simple budget is a configuration value, not a product defect. EEA source loading is now routed through the same-origin AEGIS tile proxy but its render is blocked by the retired `noise.discomap.eea.europa.eu` 2019 WMS; Overpass reports partial reliability and bounded coverage. | — | 2026-10-01 | E2E + automated | [route-matrix report](../QA/tier3-validation-develop-20261001-route-matrix/report.md), [route-matrix browser evidence](../QA/tier3-validation-develop-20261001-route-matrix/browser-evidence.md), [final 2026-09-30 T3-07/T3-09 report](../QA/tier3-validation-develop-20260930-t3-07-t3-09-final/report.md), [environmental follow-up](../QA/tier3-validation-develop-20260928-environmental/report.md), [NOAA remediation report](../QA/tier3-validation-develop-20260928-noaa/report.md) | Preserve the location-only and metadata-only recovery boundaries; revisit the manual-toggle census/elevation reachability and the default simple execution budget, and continue the remaining route matrix with exact source, coverage, and render evidence. |
| `agent.capability-discovery.inventory` | `VALIDATED` | Bounded runtime catalog pagination, result semantics, and discovery-only completion without map rendering. | The exact-lane browser run completed five successful pages (`12+12+12+12+2`) for 50 candidates, 50 unique IDs, and final `next_cursor=null`; the map session remained empty and six model calls stayed within the approved isolated `max_model_calls=6` budget. The setting was restored to `4` after restart. | This proves the bounded inventory slice only; it does not validate every provider, route family, renderer, credentialed source, or raster layer. | — | 2026-09-25 | E2E + automated | [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [browser evidence](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/browser-evidence.md), [run trace](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/inventory-run-trace.json), [focused suite](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/focused-suite.log) | Re-run after catalog pagination, runtime-budget, or discovery-route changes; keep provider and map-render boundaries separate. |
| `agent.location-resolution.core` | `VALIDATED` | Direct locations, clarification, invalid-coordinate bounds, safe recovery, and repeated location changes. | Exact-lane browser evidence passes Florence clarification while retaining Rome, canonical Milan/Texas ambiguity labels, and explicit Milan, Italy rendering. Prior Zurich bounds rejection and Springfield clarification remain linked evidence. | Other language and geography combinations remain part of the broader partial route matrix. | — | 2026-09-24 | E2E | [current browser evidence](../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md), [prior core report](../QA/core-behavior-e2e-20260919/final-report.md), [agentic search](geospatial/agentic_search.md) | Preserve clarification-before-replacement and canonical locality/region/country labels; broaden only through the exact-lane matrix. |
| `agent.location-resolution.landmarks` | `VALIDATED` | Landmark-centric location resolution and nearby-amenity routing. | Current T2-03 browser runs resolved the Colosseum and clarified central Rome to the correct Italy location, discovered `overpass_poi_amenities`, rendered the layer, and received browser acknowledgement. | Overpass reports partial reliability and roughly 2.5 km coverage; the broad keyless capability matrix remains `PARTIAL`. | — | 2026-09-23 | E2E | [T2 retry report](../QA/tier2-validation-develop-20260923-retry/report.md), [browser evidence](../QA/tier2-validation-develop-20260923-retry/browser-evidence.md), [agentic search](geospatial/agentic_search.md) | Expand to the remaining landmark and POI catalog routes without promoting provider-reported counts to independent ground truth. |
| `agent.map-render-ack-recovery` | `PARTIAL` | Candidate map preparation, browser acknowledgement, failed-render recovery, supersession, and last-known-good preservation. | The 2026-10-01 T3-07 follow-up passes FEMA and ESA public raster source/layer loading with accepted `map.render_ack` (`raster_render_pass` for both `fema_new_orleans` and `esa_worldcover_rome`, visible pixels, attribution, zero direct-upstream requests through the same-origin tile proxy), resolving ISSUE-002's FEMA/ESA component. Current exact-lane Colosseum recovery, NOAA/USGS/Census render acknowledgement, vector composition/removal, and controlled recovery evidence remain scoped PASS. The GEO-FOCUS-16 EEA run reached provider execution and prepared a candidate, but the configured `noise.discomap.eea.europa.eu` 2019 WMS is retired upstream (404 from EEA's own server), so no EEA raster renders; the last-known-good map preservation message remained visible. The earlier `develop@be61298` FEMA and ESA failures are historical (remediated by T3-07). | `ISSUE-002` is resolved for FEMA/ESA by the T3-07 raster remediation. Remaining boundaries: EEA raster render is blocked by the retired upstream WMS (external, not a repository defect); single-viewport FEMA+partner composition remains limited by NFHL layer 28 scale-dependency (needs zoom >= 14; tested partners do not render/overlap); live (non-controlled) failed-render recovery, supersession, and last-known-good preservation remain controlled-evidence only (CONTROLLED-FAULT module). | EEA source/layer acknowledgement remains the prerequisite for EEA-raster-dependent composition and recovery claims; FEMA/ESA source/layer acknowledgement now passes. | 2026-10-01 | E2E + controlled | [2026-10-01 T3-07 report](../QA/tier3-validation-develop-20261001-t3-07-final/report.md), [2026-10-01 browser evidence](../QA/tier3-validation-develop-20261001-t3-07-final/browser-evidence.md), [raster diagnostics](../QA/tier3-validation-develop-20261001-t3-07-final/T3-07/reports/RASTER-LIVE-DIAGNOSTICS.json), [environmental follow-up](../QA/tier3-validation-develop-20260928-environmental/report.md), [environmental browser evidence](../QA/tier3-validation-develop-20260928-environmental/browser-evidence.md), [map-rendering report](../QA/tier3-validation-develop-20260926-map-rendering/report.md), [NOAA remediation report](../QA/tier3-validation-develop-20260928-noaa/report.md), [raster remediation report](../QA/tier3-validation-develop-20260928-raster-remediation/report.md), [request diagnostics](../QA/tier3-validation-develop-20260928-raster-diagnostics/report.md), [controlled module](../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/full-module.log) | Preserve fail-closed acknowledgement behavior; retry EEA in the exact lane after the manifest is re-pointed to the current EEA noise service, and retest live raster failure-recovery once a raster renders. |

### Geospatial data, maps, and integrations

| Component | Status | Scope | Evidence | Known Issues | Blocker | Last Validated | Validation Level | Related Docs | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `providers.normalized-adapters` | `PARTIAL` | Provider registry, normalized feature/raster/metadata responses, attribution, stale/empty/error semantics, and selected live adapters. | The 2026-09-25 live run verified a pharmacy-only Overpass query with ten `pharmacy` records, `ok`/not-stale/not-truncated evidence, and visible OSM attribution; the exact lane also returned 24-row Open-Meteo weather and air-quality windows. The 2026-09-26 browser run additionally verified Census hydrography and USGS water-gauge composition with visible provider attributions. The 2026-09-28 GEO-FOCUS-16 follow-up verified PVGIS `metadata` normalization with a numeric annual estimate and EEA `raster` retrieval with attribution. The 2026-10-01 route-matrix continuation verifies EEA provider retrieval and now routes its WMS descriptor through the same-origin AEGIS tile proxy (0 direct-upstream browser requests). | EEA retrieval works and is proxied, but the configured `noise.discomap.eea.europa.eu` 2019 WMS is retired (404 from EEA's own server), so its render stays blocked until the manifest is re-pointed to the current EEA noise service; broader Census/USGS/catalog coverage remains incomplete. The Overpass provider continues to advertise partial general reliability. | — | 2026-10-01 | E2E + automated | [route-matrix report](../QA/tier3-validation-develop-20261001-route-matrix/report.md), [environmental follow-up](../QA/tier3-validation-develop-20260928-environmental/report.md), [live raster report](../QA/tier3-validation-develop-20260928-raster-live/report.md), [vector-composition report](../QA/tier3-validation-develop-20260926-vector-composition/report.md), [provider framework](geospatial/providers/provider_framework.md) | Re-point the EEA manifest to a live EEA noise service when the current END-2022 service is confirmed, then run the broader provider smoke matrix while preserving distinct upstream, routing, credential, and renderer outcomes. |
| `maps.basemap-switching` | `VALIDATED` | Supported basemap rendering, switching, manual preference preservation, and return to a stable map. | Core browser report verified supported basemap switches and Dark-basemap persistence across ten location changes. The 2026-09-26 live run additionally rendered Dark Basemap and OpenTopoMap Terrain over the current USGS map and confirmed a successful manual recovery clears the prior warning. | Reload/new-chat reset to the documented catalog default by design; this does not prove every public raster source. | — | 2026-09-26 | E2E | [Tier 3 report](../QA/tier3-validation-develop-20260926-map-rendering/report.md), [browser evidence](../QA/tier3-validation-develop-20260926-map-rendering/browser-evidence.md), [frontend architecture](architecture/frontend_architecture.md), [state preservation](ui/state_preservation.md) | Re-run the switch/persistence flow after renderer or session-state changes and keep source-specific failures separate. |
| `maps.vector-overlays` | `VALIDATED` | Demonstrated GeoJSON/point/line/polygon overlay rendering and visible attribution for selected public paths. | The 2026-09-26 exact-lane run retrieved 48 USGS gauges, rendered the clustered point layer with USGS attribution, exercised hide/show visibility (`1/1` → `0/1` → `1/1`), rendered 13 Census hydrography features, composed both public vector layers (`2/2`, 13 + 2 rendered), and selectively removed USGS while retaining Census. The 2026-09-28 exact-lane NOAA request rendered the affected-zone `GeometryCollection` with NOAA attribution. The 2026-10-01 T3-10 slice renders USGS earthquakes clustered points with USGS attribution and an accepted `map.render_ack`, and proves the bounded valid-empty boundary returns an honest no-results outcome (this required surgical vector spatial/temporal scope coverage and normalized point-feature intersection). The 2026-10-01 T3-12 slice renders Overpass residential building footprints as polygons and POI amenities as clustered points with OSM attribution and an accepted `map.render_ack`, plus an honest bounded valid-empty outcome. Coastal stations, atmospheric points, and historical NOAA valid-empty behavior remain additional selected paths. | This is a demonstrated subset, not proof of the complete catalog; other vector families and NOAA valid-empty behavior remain unrun. | — | 2026-10-01 | E2E | [T3-12 slice report](../QA/tier3-validation-develop-20261001-t3-10-t3-14/T3-12/report.md), [T3-12 browser evidence](../QA/tier3-validation-develop-20261001-t3-10-t3-14/T3-12/browser-evidence.md), [T3-10 slice report](../QA/tier3-validation-develop-20261001-t3-10-t3-14/T3-10/report.md), [T3-10 browser evidence](../QA/tier3-validation-develop-20261001-t3-10-t3-14/T3-10/browser-evidence.md), [map-rendering report](../QA/tier3-validation-develop-20260926-map-rendering/report.md), [NOAA remediation report](../QA/tier3-validation-develop-20260928-noaa/report.md), [vector-composition report](../QA/tier3-validation-develop-20260926-vector-composition/report.md), [vector browser evidence](../QA/tier3-validation-develop-20260926-vector-composition/browser-evidence.md), [frontend architecture](architecture/frontend_architecture.md), [geospatial validation](geospatial/ingestion/validation.md) | Expand the matrix while keeping visible source/layer and acknowledgement evidence for every map claim. |
| `maps.raster-overlays` | `PASS` | Raster, WMS, and WMTS descriptor execution through the real MapLibre renderer. | The manifest-backed AEGIS tile proxy, native map-plan proxy descriptor, explicit FEMA layer `28`, ESA Terrascope WMS construction, GIBS WMTS/WMS selection, RainViewer recent-frame proxy, current-head fail-closed raster visibility contract, focused tests, and strict audit pass. The 2026-10-01 T3-07 follow-up proves browser-authoritative FEMA and ESA raster loading: both scenarios classify `raster_render_pass` with accepted `map.render_ack`, visible pixels, attribution, and zero direct-upstream browser requests. FEMA reaches the US-egress-restricted `hazards.fema.gov` through FEMA's official ArcGIS Online relay; raster results satisfy `spatial_scope_applied`; scale-dependent NFHL layer 28 is presented at a visible zoom. The 2026-10-01 route-matrix continuation adds `eea` to the proxied raster-provider set: EEA retrieval and same-origin proxy transport pass (0 direct-upstream requests) but the configured 2019 WMS is retired upstream (404), so no EEA pixels render until the manifest is re-pointed. RainViewer keeps provider-supplied opaque recent paths, color scheme `2`, max zoom `7`, and no forecast/nowcast/IR semantics. | A single-viewport FEMA+partner composition is limited by NFHL layer 28's scale-dependency (tested partners ESA WMS, USGS gauges, GIBS, Census do not render/overlap at zoom 14+). | — | 2026-10-01 | E2E + automated | [2026-10-01 T3-07 report](../QA/tier3-validation-develop-20261001-t3-07-final/report.md), [2026-10-01 browser evidence](../QA/tier3-validation-develop-20261001-t3-07-final/browser-evidence.md), [2026-10-01 raster diagnostics](../QA/tier3-validation-develop-20261001-t3-07-final/T3-07/reports/RASTER-LIVE-DIAGNOSTICS.json), [final 2026-09-30 T3-07/T3-09 report](../QA/tier3-validation-develop-20260930-t3-07-t3-09-final/report.md), [RainViewer browser evidence](../QA/tier3-validation-develop-20260930-t3-07-t3-09-final/T3-09/live-browser/browser-evidence.md), [FEMA transport evidence](../QA/tier3-validation-develop-20260930-t3-07-t3-09-final/T3-07/network-summary.json) | Preserve the exact-lane RainViewer proof and the FEMA relay transport; retry FEMA+partner composition only when a partner renders/overlaps at the FEMA-required zoom. |
| `maps.state-preservation` | `PARTIAL` | Overlay removal, visible-state narration, basemap preference, composition, and retaining an existing overlay during changes. | Existing Census/USGS composition and selective removal remain supported by prior evidence. FEMA now renders standalone with accepted acknowledgement; FEMA+partner composition remains limited because NFHL layer 28 is scale-dependent (needs zoom >= 14) and tested partners (ESA WMS, USGS gauges, GIBS, Census) do not render or overlap at that zoom. | The FEMA composition/retention boundary is documented as limited by layer-28 scale-dependency, not by a renderer defect. | A partner that renders/overlaps at the FEMA-required zoom is needed before GEO-HYD-05/GEO-HYD-06 can complete. | 2026-10-01 | E2E | [2026-10-01 T3-07 report](../QA/tier3-validation-develop-20261001-t3-07-final/report.md), [vector-composition report](../QA/tier3-validation-develop-20260926-vector-composition/report.md), [state preservation](ui/state_preservation.md) | Continue composition/removal across rendered overlays; retry FEMA composition only with a partner that renders at the FEMA-required zoom. |
| `providers.credentialed-and-local-source-access` | `BLOCKED` | Credentialed providers and configured local feeds or snapshots such as OpenAQ, TomTom, OpenTripMap, Windy, Google Maps, ArcGIS, NASA FIRMS, GTFS, Overture, Open Charge Map, and local cameras. | Recent live reports explicitly excluded these paths because required credentials, snapshots, feeds, or local datasets were absent. | Absence in this environment is not an application defect. | Approved credentials and/or configured local source artifacts are unavailable. | — | None | [access overview](geospatial/providers/access_overview.md), [provider sources](geospatial/providers/public_and_optional_sources.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Configure only approved sources, then run the dedicated provider and browser checks without exposing secrets. |
| `geospatial.dataset-ingestion` | `PARTIAL` | Dataset-ingestion manifests, CSV/GeoJSON materialization, checksums, source health, and optional heavy-format handling. | The 2026-10-01 T4A slice establishes the ID-to-scenario mapping and passes the deterministic isolated contract: `T4-01` CSV, `T4-02` GeoJSON, and `T4-08` catalog-only descriptors are `PASS` (24 focused + 81 descriptor/API tests, 86-manifest strict audit, 6 fixture manifests materialized with functional health). The rollback/cleanup probe confirms `execute_ingestion_plan` raises on checksum/`minFeatureCount`/bbox failures but leaves partial raw/metadata/normalized artifacts behind; heavy formats return a designed partial health result. | Heavy GIS formats, configured external datasets, camera feeds, credentialed providers, live downloads, browser rendering, and the durable rollback/cleanup contract remain unvalidated or open. | — | 2026-10-01 | automated | [T4A slice report](../QA/tier4a-dataset-ingestion-20261001/report.md), [focused suite](../QA/tier4a-dataset-ingestion-20261001/focused-suite.log), [configured-source materialization](../QA/tier4a-dataset-ingestion-20261001/configured-source-materialization.json), [rollback/cleanup probe](../QA/tier4a-dataset-ingestion-20261001/rollback-cleanup-probe.json), [dataset ingestion](geospatial/ingestion/dataset_ingestion.md), [ingestion validation](geospatial/ingestion/validation.md) | Decide and implement a durable rollback/cleanup contract for failed materializations, then install the optional `geospatial-ingestion` extra for the heavy-format path; re-run after any ingestion change. |

### UI, quality, delivery, and coverage

| Component | Status | Scope | Evidence | Known Issues | Blocker | Last Validated | Validation Level | Related Docs | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ui.chat-map-workspace` | `VALIDATED` | Startup-to-chat flow, clarification, map controls, transcript hygiene, recovery, and repeated core location use. | Current exact-lane evidence shows Rome transcript/map, Florence clarification before replacement with visible acknowledgement, and canonical Milan choices followed by an attributed, acknowledged Italy map. DSML protocol-looking finalizer content remains suppressed. | Broad route families, source/raster behavior, and complete provider/browser coverage remain separate partial gates. | — | 2026-09-24 | E2E | [frontend architecture](architecture/frontend_architecture.md), [core report](../QA/core-behavior-e2e-20260919/final-report.md), [current T2 report](../QA/tier2-validation-develop-20260924-head77c5d67/report.md), [browser evidence](../QA/tier2-validation-develop-20260924-head77c5d67/browser-evidence.md) | Keep location clarification, visible `map.render_ack`, attribution, and transcript hygiene in the browser smoke. |
| `ui.settings-provider-access` | `VALIDATED` | Settings sections for model selection, model-provider credentials, local runtime, geospatial access, and persisted application runtime configuration. | T1-09 navigation/drafts and T1-10 credential lifecycle both pass. T1-10 validates masked state, safe model/geospatial save and clear, blank/invalid drafts, unreadable credentials, API failures, and the targeted selected-model response. See the [T1-10 report](../QA/tier1-validation-develop-20260923/T1-10/report.md). | Live provider authentication/connectivity remains outside this UI gate and is tracked separately as blocked provider access/parity. | — | 2026-09-23 | integration/E2E | [frontend architecture](architecture/frontend_architecture.md), [access overview](geospatial/providers/access_overview.md), [user settings](user/settings_and_access.md), [runtime validation](../QA/settings-runtime-validation-20260921.md), [T1-09 report](../QA/tier1-validation-develop-20260923/T1-09/report.md), [T1-10 report](../QA/tier1-validation-develop-20260923/T1-10/report.md) | Continue campaign at T2-01; rerun the Settings flow after credential UI or API contract changes. |
| `validation.application-foundations-tier1` | `VALIDATED` | Tier 1 route, state, conversation, realtime, run, API, jobs, Settings, credential, model, and context foundations. | T1-10 passed on `develop@8e32f82e3f094e5fb17c3978fad69b9f80b7af0b`; Tier 1 remains 12 `PASS`. The current campaign roll-up is 38 `PASS` / 3 `PARTIAL` / 2 `BLOCKED` / 25 `UNRUN` after the 2026-10-01 T4A dataset-ingestion slice (which opened `T4-01`–`T4-08`), the 2026-10-01 T3-07 raster remediation, and the 2026-10-01 T3-10 USGS earthquakes and T3-12 Overpass slices. | Broader downstream live/browser/provider coverage remains open; the public FEMA source-load/composition boundary and other provider families remain separately classified. | - | 2026-10-01 | integration/E2E | [validation strategy](validation/strategy.md), [final 2026-09-30 T3-07/T3-09 report](../QA/tier3-validation-develop-20260930-t3-07-t3-09-final/report.md), [2026-10-01 T4A slice](../QA/tier4a-dataset-ingestion-20261001/report.md), [Tier 1 checklist](validation/tier1_application_foundations.md) | Complete the remaining partial and unrun slices while keeping browser, provider, and exact-head CI boundaries distinct. |
| `quality.pyright-strict` | `VALIDATED` | Strict repository-wide Python typing gate. | The current Tier 0 sweep reports 0 errors, 0 warnings, and 0 informations under `app/server/pyproject.toml`; Python source compilation also passed for 410 files. | — | — | 2026-09-22 | integration | [Tier 0 final report](../QA/tier0-validation-develop-20260922/final/report.md), [testing and quality](coding/testing_and_quality.md), [gate ledger](validation/gate_status.md) | Rerun the full strict project configuration after typing or project-configuration changes. |
| `quality.ruff-and-frontend-regressions` | `VALIDATED` | Repository-wide Ruff, Angular production build, frontend state helper, and Karma regression suite. | The current-head remediation passes full Ruff, Pyright, 1,034 backend unit tests, the Angular production build, and 264/264 Karma tests; the strict manifest auditor reports 86 manifests with 0 errors and 0 warnings. | Existing frontend sanitizer/deprecation diagnostics remain non-failing warnings. | — | 2026-09-30 | integration | [current-head follow-up](../QA/tier3-remediation-20260930/current-head-followup-889066b3.md), [Tier 0 final report](../QA/tier0-validation-develop-20260922/final/report.md), [testing and quality](coding/testing_and_quality.md), [gate ledger](validation/gate_status.md) | Rerun the relevant frontend suite when frontend or shared contract files change. |
| `validation.environment-startup-tier0` | `VALIDATED` | Tier 0 environment, current SQLite/Alembic schema, legacy Settings migration, Windows startup, and API composition slices. | The exact-head follow-up passes fresh/warm official-launcher readiness, simulated provider-outage startup, changed-owner/PID-reuse protection, injected backend/frontend readiness-failure cleanup, canonical-state protection, and final port cleanup. The unavailable historical timing comparator is recorded as non-gating rather than a partial product result. | Downstream validation remains partial or unrun; no Tier 0 defect is evidenced. | — | 2026-09-28 | integration | [follow-up report](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md), [2026-09-28 raster report](../QA/tier3-validation-develop-20260928-raster/report.md), [timing results](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/timing-results.md), [safety harness](../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/launcher-safety-harness.json), [gate ledger](validation/gate_status.md) | Preserve the functional startup safety boundary and continue the remaining downstream slices. |
| `testing.complete-live-matrix` | `PARTIAL` | Complete live provider, browser, raster, composition, and coverage scenario matrix. | The controlled acknowledgement module and scoped location, NOAA, USGS/Census vector, composition/removal, visibility, basemap, exact provider readiness, GEO-FOCUS-16, FEMA/ESA raster, and RainViewer evidence remain valid. The 2026-10-01 T3-07 follow-up closes FEMA and ESA public raster loading with accepted `map.render_ack` (`raster_render_pass` for both standalone scenarios). The 2026-10-01 route-matrix continuation passes Acropolis, Open-Meteo aliases, generic-infrastructure clarification, and the weather-forecast row (at an adequate runtime budget); keeps census demographics, numeric elevation, and imagery extent `PARTIAL`; and routes EEA through the same-origin proxy (render still blocked by the retired upstream). | FEMA+partner composition is limited by NFHL layer 28's scale-dependency; census demographics / numeric elevation are manual-toggle unreachable; imagery extent fails render-scope validation; EEA render is blocked by upstream retirement; the default simple execution budget is a configuration value (the weather forecast passes when raised); provider parity, credentialed/local sources, dataset ingestion, broad recovery, and remaining Tier 3–5 rows remain incomplete. | T3-07 is PASS (FEMA/ESA standalone raster); T3-08 and T3-09 are PASS; GEO-HYD-05/06 remain limited by the FEMA layer-28 zoom constraint; GEO-FOCUS-16 is PARTIAL on EEA render (upstream retired); MATRIX-22 remains partial. | 2026-10-01 | E2E + automated | [route-matrix report](../QA/tier3-validation-develop-20261001-route-matrix/report.md), [route-matrix diagnostics](../QA/tier3-validation-develop-20261001-route-matrix/reports/ROUTE-MATRIX-LIVE.json), [2026-10-01 T3-07 report](../QA/tier3-validation-develop-20261001-t3-07-final/report.md), [final 2026-09-30 report](../QA/tier3-validation-develop-20260930-t3-07-t3-09-final/report.md), [controlled module](../QA/tier2-validation-develop-20260924-head66008da/controlled-fault/full-module.log) | Revisit the manual-toggle census/elevation reachability and the default simple execution budget, re-point the EEA manifest to a live service, and continue the remaining route, raster-composition, provider-parity, ingestion, recovery, and release rows with the exact provider/model and browser-authoritative evidence. |
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
- **Severity:** `HIGH` (resolved 2026-10-01 for FEMA/ESA source loading).
- **Description and impact:** FEMA and ESA now return usable raster
  descriptors AND load through the same-origin AEGIS tile proxy with accepted
  `map.render_ack`. The historical blocker was FEMA's US-egress restriction:
  `hazards.fema.gov` resets the TLS handshake for all non-US networks (and
  intermittently for some US ASNs), which is why the REST/WMS, pooled-client,
  fresh-httpx, and native-curl matrix failed before status or an image
  response. FEMA is now reached through FEMA's official ArcGIS Online relay
  (the same relay FEMA's own NFHL Viewer uses). FEMA + USGS composition and
  retaining FEMA after partner removal remain limited by NFHL layer 28's
  scale-dependency (needs zoom ≥ 14; tested partners do not render/overlap at
  that zoom), which is an upstream data property, not a renderer defect.
- **Evidence:** [2026-10-01 T3-07 report](../QA/tier3-validation-develop-20261001-t3-07-final/report.md),
  [2026-10-01 browser evidence](../QA/tier3-validation-develop-20261001-t3-07-final/browser-evidence.md),
  [2026-10-01 raster diagnostics](../QA/tier3-validation-develop-20261001-t3-07-final/T3-07/reports/RASTER-LIVE-DIAGNOSTICS.json),
  [2026-09-20 focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md),
  [hazard/hydrology rerun](../QA/aegis-hazard-hydrology-e2e-20260920/report.md),
  [descriptor boundary report](../QA/tier3-validation-develop-20260928-raster/report.md),
  and [sanitized backend diagnostics](../QA/tier3-validation-develop-20260929-raster-followup/backend-raster-diagnostics.log).
- **Repository defects found and fixed:** the follow-up repaired lost upstream
  raster diagnostics, nested native raster descriptor fields, provider-layer
  tool exposure, point-to-bbox discovery scope, GIBS layer paging/fallback,
  GIBS matrix-set zoom ceilings, and harness capability correlation. The
  2026-10-01 remediation additionally routes FEMA through FEMA's official
  ArcGIS Online relay with the required `Origin`/`Referer` headers, declares
  raster `spatial_scope_satisfied` coverage, and presents scale-dependent NFHL
  layer 28 at a visible zoom. Focused regressions and strict Pyright pass.
- **External/provider boundary:** the final FEMA target uses explicit layer
  `28`; FEMA is now reachable through the official relay from any egress. ESA
  uses the corrected Terrascope WMS route. RainViewer is a separate
  backend-owned recent-radar path and must not be used to infer FEMA health.
- **Blocker:** The FEMA public source boundary is resolved; FEMA and ESA
  standalone raster rendering and acknowledgement pass. A single-viewport
  FEMA+partner composition remains limited by NFHL layer 28's scale-dependency
  (tested partners ESA WMS, USGS gauges, GIBS, and Census do not render or
  overlap at the required zoom 14+).
- **Remediation status:** Resolved 2026-10-01 for FEMA/ESA source loading;
  `maps.raster-overlays` and `agent.map-render-ack-recovery` reflect the
  validated FEMA/ESA render acknowledgement. The dependent FEMA composition
  boundary is documented as limited by layer-28 scale-dependency.
- **Required revalidation:** FEMA and ESA WorldCover standalone rows now show
  visible source/layer state and `map.render_ack`; retain the request-level
  diagnostic capture for any future failure. The exact-lane RainViewer
  bootstrap and browser acknowledgement are already recorded separately.
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
  a numeric metadata-only solar estimate for Rome. EEA noise reaches provider
  retrieval and returns an attributed renderable raster descriptor; its WMS
  descriptor is now routed through the same-origin AEGIS tile proxy, but the
  configured 2019 WMS is retired upstream (404), so the render stays blocked.
  RainViewer has functional browser evidence and passes the disposable exact
  lane and browser acknowledgement. The 2026-10-01 route-matrix continuation
  passes Acropolis semantics, Open-Meteo air/weather aliases, and
  generic-infrastructure clarification; the weather-forecast row passes once
  the runtime budget is adequate (the default `simple_max_model_calls=4` is a
  configuration value, not a product defect); Census demographics and numeric
  elevation are unreachable because their capabilities are `defaultEnabled:false`
  manual-toggle; imagery extent fails backend render-scope validation. The
  complete user-language capability claim remains open.
- **Suspected cause:** Causes vary by capability and are not collapsed into a
  single unverified root cause. The census/elevation unreachability points to
  the `agenticUse.defaultEnabled` manual-toggle contract; the earlier
  weather-budget exhaustion pointed to the runtime execution budget
  configuration.
- **Remediation status:** Partially remediated 2026-10-01; PVGIS is `PASS`,
  RainViewer is `PASS` for the exact lane and browser acknowledgement, Acropolis
  and Open-Meteo aliases pass, generic-infrastructure clarification passes, the
  weather-forecast row is `PASS` at an adequate runtime budget, EEA is `PARTIAL`
  (proxied but upstream-retired), and Census demographics / numeric elevation /
  imagery extent stay open.
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
| `HIST-005` `providers.fema.arcgis-endpoint` | FEMA descriptor retrieval used an obsolete or unusable endpoint. | The current catalog/adapter pins ArcGIS NFHL layer `28` and constructs the bounded export descriptor; the 2026-09-30 transport matrix still fails before an upstream image response, so browser source loading remains active `ISSUE-002`. | FEMA adapter, raster descriptor, or MapLibre source changes. |
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
| `agent.capability-routing.live-language` | `PARTIAL` | Census demographics and numeric elevation are unreachable via the manual-toggle contract; imagery extent fails render-scope validation; the weather forecast passes only when the default simple execution budget is raised; remaining route aliases and semantics and other live catalog families stay open. | `HIGH` | Revisit the manual-toggle reachability and the default simple execution budget, then execute the remaining rows using the exact configured lane and browser-authoritative source/render evidence. |
| `agent.capability-discovery.inventory` | `VALIDATED` | No current gap in the bounded 50-candidate discovery-only slice. | — | Re-run after catalog pagination, runtime-budget, or discovery-route changes; keep provider and map-render boundaries separate. |
| `testing.complete-live-matrix` | `PARTIAL` | Full required provider, raster, composition, coverage, multilingual, and recovery rows. | `HIGH` | Execute the remaining rows with the exact configured lane and browser-authoritative evidence. |
| `model.provider-parity.openai-ollama` | `BLOCKED` | Provider-specific continuation and structured-output evidence. | `HIGH` | Supply the approved service/credential boundary and run each lane independently; never silently substitute. |
| `geospatial.dataset-ingestion` | `PARTIAL` | Representative materialization, checksum, source-health, and optional-format behavior. | `MEDIUM` | The deterministic isolated fixture path passes (`T4-01`/`T4-02`/`T4-08` PASS); configure a real source, install the optional heavy-format extra, and implement/validate the durable rollback/cleanup contract for the remaining T4A rows. |
| `providers.credentialed-and-local-source-access` | `BLOCKED` | Approved credentialed provider runs and configured local snapshots/feeds. | `MEDIUM` | Configure only authorized sources, then run the provider smoke and relevant UI/map checks. |

## Update boundary

When evidence changes, update the smallest affected component row, issue, or
validation-debt entry. Keep active defects out of the resolved section, keep
validation debt separate from defects, and link to the detailed report that
establishes the conclusion. The invariant is:

> `project_status_ledger.md` represents the canonical current operational
> state; detailed architecture and validation documents explain the contracts
> and evidence used to establish that state.
| `ci.hosted-exact-head` | `VALIDATED` | Hosted CI result for an exact pushed branch head. | GitHub Actions push run 36692241300 completed successfully with all four jobs green for exact implementation/evidence commit `develop@bd1fe60b1e272936bc7b02d284c7bcc48d064acb`. The later ledger reconciliation is documentation-only and does not replace that workflow target. | Hosted CI is tied to the recorded evidence SHA and does not substitute for live-provider/render evidence. | — | 2026-09-30 | hosted CI | [gate status](validation/gate_status.md), [2026-09-30 T3-07/T3-09 report](../QA/tier3-validation-develop-20260930-t3-07-t3-09/report.md), [hosted workflow result](../QA/tier3-validation-develop-20260930-t3-07-t3-09/hosted-ci.json), [GitHub Actions run 36692241300](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36692241300) | Recheck hosted CI on the exact SHA after the next implementation or evidence push; keep the source SHA and workflow conclusion paired. |
