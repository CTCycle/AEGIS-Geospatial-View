# Project Status Ledger

Last updated: 2026-09-22

This is the canonical high-level catalog of the current operational state of
AEGIS Geospatial View. The repository snapshot used for this update is
`loop-dev` after the requested pre-work checkpoint `8ed88699`; the documentation
change itself follows that checkpoint. Detailed reports explain how a status
was established, while this ledger records the current conclusion.

**Current project posture: `PARTIAL`.** The native runtime and core browser
interaction paths have meaningful local and manual proof. The complete live
geospatial matrix, several public-provider routes, live raster rendering,
strict repository typing, hosted CI, and some optional integrations remain
incomplete or unvalidated.

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
| `runtime.startup.windows-local` | `PARTIAL` | Windows launcher port-consent guard, warm dependency/build reuse, concurrent backend/frontend startup, and isolated no-op database startup. | Local Windows launcher and browser checks plus 401 backend, 248 Angular, and 19 frontend-state tests; details in the [startup optimization report](../QA/startup-optimization-20260922/report.md). | No paired same-machine pre-change timing; dynamic-provider outage, protected-process/ownership-change races, and injected service-failure cleanup remain unverified. Angular `ng serve` still compiles at launch. | — | 2026-09-22 | E2E + automated | [startup](runtime/startup.md), [runtime modes](runtime/modes.md), [optimization report](../QA/startup-optimization-20260922/report.md) | Capture paired before/after warm timings and exercise provider-outage and failed-start cleanup paths. |
| `catalog.manifests-and-auditor` | `VALIDATED` | Runtime catalog loading and strict production manifest audit. | Latest focused report records 86 manifests, 0 errors, and 0 warnings. | Catalog coverage is not the same as live-provider or browser-render proof. | — | 2026-09-20 | integration | [manifest contract](geospatial/manifests/manifest_contract.md), [ingestion validation](geospatial/ingestion/validation.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Re-run the strict production auditor after manifest or runtime-profile changes. |
| `backend.agent.native-loop` | `VALIDATED` | Native route, typed tool exposure, observation/recovery cycle, bounded context, and terminal completion contracts. | Native gate rows for routing, state, finalization, render admission, and focused regression suites are passing; the latest focused slice reported 117 passed. | Live provider and full browser coverage remain separate gates. | — | 2026-09-20 | integration | [native harness](geospatial/native_harness_bootstrap.md), [gate ledger](validation/gate_status.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Re-run the focused native suite after agent-loop, route, policy, or tool changes. |
| `backend.run-lifecycle-and-persistence` | `VALIDATED` | SQLite migrations, revisioned conversation state, durable run events, terminal finalization, and last-known-good presentation preservation. | Migration and terminal-presentation gates are passing in the detailed validation ledger. | No current defect is evidenced in the tested local scope. | — | 2026-09-17 | integration | [persistence](architecture/persistence.md), [native harness](geospatial/native_harness_bootstrap.md), [gate ledger](validation/gate_status.md) | Re-run isolated Alembic and run-lifecycle tests after schema or persistence changes. |
| `backend.api.sync-chat-turn` | `PARTIAL` | Synchronous chat-turn response boundary and orchestration smoke behavior. | The detailed gate ledger records a typed 409 while `/api/chat/turn` is still running. | `ISSUE-003`: terminal response timing is not yet explicit for this API path. | — | 2026-09-17 | integration | [backend API](architecture/backend_api.md), [gate ledger](validation/gate_status.md) | Define or await the synchronous boundary, then rerun isolated API orchestration checks. |
| `model.opencode-go.deepseek-v4.1-flash` | `VALIDATED` | Exact configured provider/model lane readiness and visible selection without silent fallback. | Structured provider probe passed in the gate ledger; 2026-09-19/20 browser reports observed the exact lane and no fallback. | Readiness does not prove every geospatial scenario or provider parity. | — | 2026-09-20 | E2E | [configuration](runtime/configuration.md), [gate ledger](validation/gate_status.md), [hazard rerun](../QA/aegis-hazard-hydrology-e2e-20260920/report.md) | Preserve the exact lane in future revalidation and record any provider change explicitly. |
| `model.provider-parity.openai-ollama` | `BLOCKED` | Provider-specific continuation and structured-output proof outside the exercised OpenCode Go lane. | Native implementation documents say OpenAI Responses and Ollama remain unrun; the live boundary retains Ollama-unavailable behavior rather than falling back. | No current parity claim is allowed. | Required provider credentials/services were not available for the recorded validation boundary. | — | None | [native harness](geospatial/native_harness_bootstrap.md), [configuration](runtime/configuration.md), [gate ledger](validation/gate_status.md) | Run provider-specific continuation probes when each service and approved credential is available. |
| `agent.capability-routing.live-language` | `PARTIAL` | Natural-language routing and capability discovery for keyless geospatial requests. | 2026-09-20 focused matrix routed and executed several capabilities but left explicit gaps. | `ISSUE-001` and `ISSUE-006`: landmark/POI, RainViewer, EEA, PVGIS, Census, and some Open-Meteo aliases remain unreliable or unavailable through normal language. | — | 2026-09-20 | E2E | [agentic search](geospatial/agentic_search.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Review route domains, enabled catalog entries, and exact-location binding; rerun each affected scenario. |
| `agent.location-resolution.core` | `VALIDATED` | Direct locations, clarification, invalid-coordinate bounds, safe recovery, and repeated location changes. | Core browser report recorded 38 passes, 2 attention cases, correct bounds rejection, and ten consecutive coherent map updates. | Italian context such as `Mostrami Milano` remains an attention case; landmark routing is tracked separately. | — | 2026-09-19 | E2E | [core report](../QA/core-behavior-e2e-20260919/final-report.md), [agentic search](geospatial/agentic_search.md) | Re-run direct, ambiguous, multilingual, and invalid-coordinate cases after routing or location changes. |
| `agent.location-resolution.landmarks` | `BROKEN` | Landmark-centric location resolution and nearby-amenity routing. | Colosseum prompts did not discover a supported capability; a central-Rome prompt resolved Tehran before route rejection. | `ISSUE-001`: no safe, correctly located bounded POI result for the tested landmark flow. | — | 2026-09-20 | E2E | [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md), [agentic search](geospatial/agentic_search.md) | Repair landmark intent and exact geographic binding; revalidate Colosseum and central Rome with visible location evidence. |
| `agent.map-render-ack-recovery` | `PARTIAL` | Candidate map preparation, browser acknowledgement, failed-render recovery, supersession, and last-known-good preservation. | Controlled happy path passes and six controlled fault cases pass; live FEMA/ESA source loading still fails. | `ISSUE-002` and `ISSUE-005`: public raster source failures and one controlled supersession ordering failure remain. | Public source-load behavior and the unresolved supersession case prevent a complete claim. | 2026-09-20 | E2E | [gate ledger](validation/gate_status.md), [native harness](geospatial/native_harness_bootstrap.md), [hazard rerun](../QA/aegis-hazard-hydrology-e2e-20260920/report.md) | Fix the controlled supersession ordering, investigate source loading, and rerun the full acknowledgement matrix. |

### Geospatial data, maps, and integrations

| Component | Status | Scope | Evidence | Known Issues | Blocker | Last Validated | Validation Level | Related Docs | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `providers.normalized-adapters` | `PARTIAL` | Provider registry, normalized feature/raster/metadata responses, attribution, stale/empty/error semantics, and selected live adapters. | Focused unit tests and the 2026-09-20 live slice validated NOAA, Open-Meteo point paths, USGS, Overpass residential, and NOAA CO-OPS. | FEMA retrieval works but its raster does not load in MapLibre; GIBS was upstream-unavailable; Census and several cataloged paths remain incomplete. | — | 2026-09-20 | E2E | [provider framework](geospatial/providers/provider_framework.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Run the provider smoke matrix and preserve distinct upstream, routing, credential, and renderer outcomes. |
| `maps.basemap-switching` | `VALIDATED` | Supported basemap rendering, switching, manual preference preservation, and return to a stable map. | Core browser report verified supported basemap switches and Dark-basemap persistence across ten location changes. | Reload/new-chat reset to the documented catalog default by design. | — | 2026-09-19 | E2E | [frontend architecture](architecture/frontend_architecture.md), [state preservation](ui/state_preservation.md), [core report](../QA/core-behavior-e2e-20260919/final-report.md) | Re-run the switch/persistence flow after renderer or session-state changes. |
| `maps.vector-overlays` | `VALIDATED` | Demonstrated GeoJSON/point/line/polygon overlay rendering and visible attribution for selected public paths. | Residential buildings, earthquakes, coastal stations, atmospheric points, USGS gauges, Census hydrography, and NOAA valid-empty behavior passed in recent live runs. | This is a demonstrated subset, not proof of the complete catalog. | — | 2026-09-20 | E2E | [frontend architecture](architecture/frontend_architecture.md), [geospatial validation](geospatial/ingestion/validation.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Expand the matrix while keeping visible source/layer and acknowledgement evidence for every map claim. |
| `maps.raster-overlays` | `PARTIAL` | Raster, WMS, and WMTS descriptor execution through the real MapLibre renderer. | NOAA radar rendered and acknowledged; FEMA retrieval succeeded but source loading failed; ESA WorldCover source loading failed; GIBS was unavailable upstream. | `ISSUE-002`: no verified FEMA or WorldCover pixels in the affected runs. | Public source-load/provider boundaries remain unresolved. | 2026-09-20 | E2E | [provider framework](geospatial/providers/provider_framework.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md), [hazard rerun](../QA/aegis-hazard-hydrology-e2e-20260920/report.md) | Investigate the failing public source/layer boundary without weakening `map.render_ack`; rerun FEMA, ESA, and GIBS cases. |
| `maps.state-preservation` | `PARTIAL` | Overlay removal, visible-state narration, basemap preference, composition, and retaining an existing overlay during changes. | Working USGS removal and committed-state narration passed; FEMA + USGS composition and FEMA retention remain blocked because FEMA never rendered. | `ISSUE-002`: retention of an unrendered FEMA overlay is not proven. | FEMA raster render is required before the composition and retention flows can complete. | 2026-09-20 | E2E | [state preservation](ui/state_preservation.md), [hazard rerun](../QA/aegis-hazard-hydrology-e2e-20260920/report.md) | Re-run composition and selective removal only after a verified FEMA source/layer acknowledgement. |
| `providers.credentialed-and-local-source-access` | `BLOCKED` | Credentialed providers and configured local feeds or snapshots such as OpenAQ, TomTom, OpenTripMap, Windy, Google Maps, ArcGIS, NASA FIRMS, GTFS, Overture, Open Charge Map, and local cameras. | Recent live reports explicitly excluded these paths because required credentials, snapshots, feeds, or local datasets were absent. | Absence in this environment is not an application defect. | Approved credentials and/or configured local source artifacts are unavailable. | — | None | [access overview](geospatial/providers/access_overview.md), [provider sources](geospatial/providers/public_and_optional_sources.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Configure only approved sources, then run the dedicated provider and browser checks without exposing secrets. |
| `geospatial.dataset-ingestion` | `UNVALIDATED` | Dataset-ingestion manifests, CSV/GeoJSON materialization, checksums, source health, and optional heavy-format handling. | Contracts and validation workflow are documented; no recent convincing end-to-end ingestion run is recorded in the current QA set. | Heavy GIS formats are intentionally optional and may remain partial. | — | — | None | [dataset ingestion](geospatial/ingestion/dataset_ingestion.md), [ingestion validation](geospatial/ingestion/validation.md) | Run a representative isolated ingestion workflow and record its artifact and source-health evidence. |

### UI, quality, delivery, and coverage

| Component | Status | Scope | Evidence | Known Issues | Blocker | Last Validated | Validation Level | Related Docs | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ui.chat-map-workspace` | `VALIDATED` | Startup-to-chat flow, clarification, map controls, transcript hygiene, recovery, and repeated core location use. | Core browser report recorded 38 passes and 2 attention cases with no core blocker. | Brief hydration blank state and `Mostrami Milano` language-aware disambiguation remain attention items. | — | 2026-09-19 | E2E | [frontend architecture](architecture/frontend_architecture.md), [core report](../QA/core-behavior-e2e-20260919/final-report.md) | Re-run the core browser smoke after user-visible UI, realtime, or map changes. |
| `ui.settings-provider-access` | `PARTIAL` | Settings sections for model selection, model-provider credentials, local runtime, geospatial access, and persisted application runtime configuration. | SQLite migration/API coverage, 177 targeted geospatial/chat regression tests, Angular production build, 30 focused Settings Karma tests, and the Tier 1 browser baseline pass the seven-section, masked-state, safe fixture save/clear, runtime save/restart, and desktop model-card checks. | Controlled unreadable-credential/API-failure states and a stale E2E `role=tab` assertion remain. | — | 2026-09-21 | integration | [frontend architecture](architecture/frontend_architecture.md), [access overview](geospatial/providers/access_overview.md), [user settings](user/settings_and_access.md), [runtime validation](../QA/settings-runtime-validation-20260921.md), [Tier 1 report](../QA/tier1-application-foundations-20260921/report.md) | Align the Settings E2E locator, then exercise controlled credential failure states. |
| `validation.application-foundations-tier1` | `PARTIAL` | Tier 1 route, state, conversation, realtime, run, API, jobs, Settings, credential, model, and context foundations. | Exact current-HEAD baseline records 6 PASS and 6 PARTIAL slices; 105 targeted backend tests, 248 Angular tests, and rendered desktop-width browser evidence are preserved in the dated QA package. | T1-02 headless MapLibre canvas boundary; T1-03 hydration coverage; T1-06 live HTTP timing; T1-07 mounted jobs/shutdown; T1-09 test-contract drift; T1-10 credential failure fixtures. | — | 2026-09-21 | integration/E2E | [validation strategy](validation/strategy.md), [Tier 1 checklist](validation/tier1_application_foundations.md), [Tier 1 ledger](../QA/tier1-application-foundations-20260921/ledger.md) | Continue at the first incomplete Tier 1 row; do not open downstream campaign claims as complete. |
| `quality.pyright-strict` | `BROKEN` | Strict repository-wide Python typing gate. | Detailed gate ledger records 46 remaining repository diagnostics; targeted changed-module typing had passed separately. | `ISSUE-004`: repository strict gate is not green. | — | 2026-09-17 | integration | [testing and quality](coding/testing_and_quality.md), [gate ledger](validation/gate_status.md) | Resolve the remaining diagnostics and rerun the full strict project configuration. |
| `quality.ruff-and-frontend-regressions` | `VALIDATED` | Ruff on changed Python files, Angular production build, and recorded frontend regression suites. | Recent reports record Ruff success; the core report records a successful production build; the gate ledger records 233/233 Karma tests. | The frontend build was not repeated for backend-only changes in the latest focused run. | — | 2026-09-20 | integration | [testing and quality](coding/testing_and_quality.md), [gate ledger](validation/gate_status.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md) | Re-run the relevant frontend build/tests when frontend or shared contract files change. |
| `testing.complete-live-matrix` | `PARTIAL` | Complete live provider, browser, raster, composition, and coverage scenario matrix. | 2026-09-20 focused matrix remains `PARTIAL`; successful vector subsets do not cover all required rows. | Explicit gaps remain for raster loading, routing, provider availability, coverage reruns, and other catalog families. | External providers and configured sources vary by environment. | 2026-09-20 | E2E | [gate ledger](validation/gate_status.md), [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md), [hazard rerun](../QA/aegis-hazard-hydrology-e2e-20260920/report.md) | Execute the missing rows and retain the exact provider/model, browser, source/layer, and acknowledgement evidence. |
| `ci.hosted-exact-head` | `UNVALIDATED` | Hosted CI result for the exact current branch head. | The detailed gate ledger records the hosted-CI gate as unrun; no current exact-head result is claimed here. | No hosted PASS or FAIL is inferred from local tests. | — | — | None | [gate ledger](validation/gate_status.md), [testing and quality](coding/testing_and_quality.md) | Inspect the workflow result for the exact pushed head before changing this status. |
| `deployment.cross-platform` | `NOT_IMPLEMENTED` | First-class Docker deployment, Linux/macOS launcher, and standalone production distribution artifact. | Runtime modes explicitly list these capabilities as not implemented. | This is a product-scope boundary, not a failed local Windows workflow. | — | — | None | [runtime modes](runtime/modes.md), [deployment](runtime/deployment.md) | Implement only if cross-platform or standalone deployment becomes an approved scope. |

## Open issues

These are current actionable problems. Severity is independent of component
status; an `UNVALIDATED` component is not automatically an issue, and a
`PARTIAL` component can have a low-severity limitation.

### ISSUE-001 — Landmark and nearby-POI routing can use the wrong geography

- **Affected component:** `agent.location-resolution.landmarks`; also
  `agent.capability-routing.live-language`.
- **Severity:** `HIGH`.
- **Description and impact:** Landmark prompts can fail to discover a supported
  nearby-amenity capability. A central-Rome prompt resolved an Embassy of Italy
  address in Tehran before route rejection, so the application must not claim a
  correct map or provider result for this flow.
- **Evidence:** `GEO-FOCUS-12` in the
  [2026-09-20 focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md).
- **Suspected cause:** Not established; do not infer one from the symptom.
- **Blocker:** None; this is an application routing and geographic-binding gap.
- **Remediation status:** Open. Review landmark intent, exact location
  references, and capability eligibility without silent substitution.
- **Required revalidation:** Colosseum/central-Rome prompts must produce the
  expected location, bounded POI capability, visible map evidence, and matching
  acknowledgement or an explicit safe clarification.
- **Related documentation:** [agentic search](geospatial/agentic_search.md),
  [focused report](../QA/aegis-geospatial-e2e-validation-20260920/report.md).

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

### ISSUE-003 — Synchronous chat-turn completion boundary is ambiguous

- **Affected component:** `backend.api.sync-chat-turn`.
- **Severity:** `MEDIUM`.
- **Description and impact:** The synchronous `/api/chat/turn` path can return
  a typed 409 while the persisted run is still executing, leaving clients
  without an explicit terminal response boundary.
- **Evidence:** The `SYNC-CHAT-TURN` row in the
  [validation gate ledger](validation/gate_status.md).
- **Suspected cause:** The endpoint boundary is not yet explicit; no stronger
  cause is asserted.
- **Blocker:** None.
- **Remediation status:** Open.
- **Required revalidation:** Isolated API orchestration must prove either
  awaited terminal hydration or an explicit asynchronous contract, including
  error and cancellation behavior.
- **Related documentation:** [backend API](architecture/backend_api.md),
  [gate ledger](validation/gate_status.md).

### ISSUE-004 — Repository-wide strict Pyright gate remains failing

- **Affected component:** `quality.pyright-strict`.
- **Severity:** `MEDIUM`.
- **Description and impact:** The strict project run still reports 46
  repository diagnostics. Targeted typing for changed modules passed, but the
  repository-level quality gate cannot be marked green.
- **Evidence:** The `PYRIGHT-STRICT` row in the
  [validation gate ledger](validation/gate_status.md).
- **Suspected cause:** Pre-existing provider Optional-access, maintenance,
  transport, and AgentLoop complexity diagnostics are recorded; do not assume
  that list is exhaustive until the next run.
- **Blocker:** None.
- **Remediation status:** Open.
- **Required revalidation:** Run the full strict configuration, not only
  changed-module or targeted diagnostics.
- **Related documentation:** [testing and quality](coding/testing_and_quality.md),
  [native harness](geospatial/native_harness_bootstrap.md).

### ISSUE-005 — Controlled supersession acknowledgement ordering still fails

- **Affected component:** `agent.map-render-ack-recovery`.
- **Severity:** `MEDIUM`.
- **Description and impact:** Six controlled browser fault cases pass, but the
  supersession case fails; a late acknowledgement can therefore remain
  unresolved in the controlled recovery matrix.
- **Evidence:** The `CONTROLLED-FAULT` row in the
  [validation gate ledger](validation/gate_status.md).
- **Suspected cause:** The recorded next action is to repair late superseded
  rejection ordering; no broader cause is asserted.
- **Blocker:** None.
- **Remediation status:** Open.
- **Required revalidation:** Rerun the entire controlled module, including
  matching, stale, conflicting, failed, and superseded acknowledgements.
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

## Validation debt

Validation debt is a priority list for future testing, not a defect list. An
entry may remain `UNVALIDATED` or `BLOCKED` without implying that the feature is
broken.

| Component | Current confidence | Missing validation | Priority | Next validation action |
| --- | --- | --- | --- | --- |
| `testing.complete-live-matrix` | `PARTIAL` | Full required provider, raster, composition, coverage, multilingual, and recovery rows. | `HIGH` | Execute the remaining rows with the exact configured lane and browser-authoritative evidence. |
| `maps.fema-coverage-guardrail` | `UNVALIDATED` | A fresh Zurich coverage-guardrail pass after the 2026-09-20 rerun became inconclusive; the earlier pass is historical only. | `HIGH` | Re-run the guardrail and prove one clarification/rejection without provider or map execution. |
| `model.provider-parity.openai-ollama` | `BLOCKED` | Provider-specific continuation and structured-output evidence. | `HIGH` | Supply the approved service/credential boundary and run each lane independently; never silently substitute. |
| `ci.hosted-exact-head` | `UNVALIDATED` | Workflow result for the exact pushed head. | `HIGH` | Inspect the exact-head workflow before claiming hosted readiness. |
| `geospatial.dataset-ingestion` | `UNVALIDATED` | Representative materialization, checksum, source-health, and optional-format behavior. | `MEDIUM` | Run isolated dataset-ingestion validation and retain the report under `assets/QA/`. |
| `ui.settings-provider-access` | `PARTIAL` | Controlled unreadable-credential and explicit API failure states beyond the completed section/navigation and safe fixture save/clear browser pass. | `MEDIUM` | Align the Settings E2E locator, then run controlled failure responses without real secrets. |
| `providers.credentialed-and-local-source-access` | `BLOCKED` | Approved credentialed provider runs and configured local snapshots/feeds. | `MEDIUM` | Configure only authorized sources, then run the provider smoke and relevant UI/map checks. |

## Update boundary

When evidence changes, update the smallest affected component row, issue, or
validation-debt entry. Keep active defects out of the resolved section, keep
validation debt separate from defects, and link to the detailed report that
establishes the conclusion. The invariant is:

> `project_status_ledger.md` represents the canonical current operational
> state; detailed architecture and validation documents explain the contracts
> and evidence used to establish that state.
