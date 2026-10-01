# Comprehensive validation strategy

Last updated: 2026-10-01

This document is the durable digest of the AEGIS comprehensive validation
roadmap, first established on `loop-dev` and continued on `develop`. It defines
the campaign order, evidence boundary, status vocabulary, and hand-off points
that future validation agents should use. The dated
scenario results live under [`../../QA/`](../../QA/); this document does not
replace those reports.

## Purpose and authority

The campaign validates the exact tested revision in dependency order:

`environment -> SQLite/migrations -> application composition -> API contracts -> frontend routing/state -> conversations/realtime -> native agent -> capability/provider execution -> map candidate -> MapLibre -> render acknowledgement -> finalization`

Source authority is divided deliberately:

- `assets/docs/project_status_ledger.md` is the current operational conclusion.
- `assets/docs/validation/gate_status.md` is the compact gate matrix.
- The dated `assets/QA/<campaign>/` package is the scenario-level evidence.
- Architecture and contract documents describe intended behavior; they do not
  promote an implementation or a provider response to validated behavior.

For map workflows, rendered browser state is authoritative. A successful HTTP
response, provider descriptor, catalog entry, or visible canvas is not enough.
The expected location and viewport, source/layer state, visible pixels where
meaningful, attribution, matching run/session/revision, and accepted
`map.render_ack` must be recorded when the workflow requires them.

## Evidence model

Every slice records these four independent facts:

| Field | Meaning |
| --- | --- |
| `feature_exists` | The source, manifest, contract, or UI surface exists. |
| `feature_exercised` | The stated scenario was actually run on the tested revision. |
| `feature_passed` | The executed scenario produced the expected result. |
| `feature_fully_passed` | Every required scenario for the slice passed. |

Do not infer `PASS` from `feature_exists=true`. Use the following campaign
statuses:

| Status | Meaning |
| --- | --- |
| `PASS` | All scenarios required by the stated slice passed. |
| `PARTIAL` | Some scenarios passed, while others failed or remain incomplete. |
| `FAIL` | A reproducible product defect blocks the slice. |
| `BLOCKED` | An external prerequisite prevents meaningful execution. |
| `UNTESTED` | The implementation exists but has not been meaningfully exercised. |
| `UNKNOWN` | Evidence conflicts, is stale, or is insufficient to classify. |
| `UNRUN` | A planned campaign tier or gate has not yet been opened. |

Provider outages, missing credentials, missing configured datasets, renderer
failures, and routing defects remain separate outcomes. A provider probe is
not a map-render result.

## Ordered campaign

The campaign contains 68 slices. Tier 0 and Tier 1 are prerequisites for
trusting downstream feature evidence.

| Campaign tier | Slice IDs | Focus | Current hand-off |
| --- | --- | --- | --- |
| Tier 0 | `T0-01`–`T0-05` | Static quality, current migration, legacy settings migration, Windows startup, and API composition. | The [2026-09-22 Tier 0 reconciliation](../../QA/tier0-validation-develop-20260922/final/report.md) passed all five on its tested boundary. The [2026-09-25 T0/T2 follow-up](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md) revalidated the exact-head Windows launcher boundary: fresh/warm readiness, outage startup, ownership/PID-reuse safety, injected cleanup, canonical-state protection, and final port cleanup pass. `T0-04` is `PASS`; its unavailable historical timing comparator is explicitly non-gating. |
| Tier 1 | `T1-01`–`T1-12` | Application foundations: routing, tab-local state, conversations, realtime, run lifecycle, HTTP chat, jobs, runtime Settings, credential lifecycle, model selection, and context presentation. | [Tier 1 checklist](tier1_application_foundations.md), [T1-10 continuation](../../QA/tier1-validation-develop-20260923/T1-10/report.md), [2026-09-23 T1-06 continuation](../../QA/tier1-validation-develop-20260923/T1-06/report.md), [T1-03 continuation](../../QA/tier1-validation-develop-20260923/T1-03/report.md), [2026-09-22 T1-02 continuation](../../QA/tier1-validation-develop-20260922/T1-02/report.md), and [2026-09-21 baseline](../../QA/tier1-application-foundations-20260921/report.md). Tier 1 remains 12/12 `PASS`. |
| Tier 2 | `T2-01` through `T2-07` | Plain and ambiguous location flows, multi-turn replacement, landmarks, capability discovery, direct tools, history, and evidence inspection. | The [2026-09-24 continuation](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md) passes `T2-01`/`T2-02` on the exact OpenCode Go lane; `T2-03` remains `PASS`. The [2026-09-25 continuation](../../QA/tier2-validation-develop-20260925-next-slices/report.md) passes the tested `T2-05`/`T2-06`/`T2-07` scenarios, and the [T0/T2 follow-up](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md) passes `T2-04` with five pages, 50 unique candidates, and `next_cursor=null` under an approved isolated six-call budget restored to four afterward. `ISSUE-001` is resolved. |
| Tier 3 | `T3-01`–`T3-18` | Basemaps, vector/raster families, valid-empty behavior, public providers, overlay mutation, composition, and map inspection controls. | `T3-01`/`T3-02`/`T3-03`/`T3-04`/`T3-05`/`T3-06`, `T3-07`, `T3-08`, and `T3-09` pass current browser-authoritative checks. `T3-07` is now `PASS`: FEMA and ESA public raster overlays load through the same-origin AEGIS tile proxy and render with accepted `map.render_ack`; FEMA reaches the US-egress-restricted `hazards.fema.gov` through FEMA's official ArcGIS Online relay, raster results satisfy the `spatial_scope_applied` requirement, and scale-dependent NFHL layer 28 is presented at a visible zoom. The dependent FEMA composition/removal mechanism is validated; a single-viewport FEMA+partner composition is limited by NFHL layer 28's scale-dependency. `T3-08` remains `PASS` after all 12 advertised GIBS cases met the browser acceptance boundary. `T3-09` is `PASS`: the exact Settings-API bootstrap persisted `opencode-go / deepseek-v4.1-flash`, the native structured probe passed, and the browser acknowledgement recorded source/layer/pixel evidence. See the [2026-10-01 T3-07 report](../../QA/tier3-validation-develop-20261001-t3-07-final/report.md), [final 2026-09-30 T3-07/T3-09 report](../../QA/tier3-validation-develop-20260930-t3-07-t3-09-final/report.md), [raster-provider-fixes follow-up](../../QA/tier3-validation-develop-20260929-raster-provider-fixes/report.md), [environmental follow-up](../../QA/tier3-validation-develop-20260928-environmental/report.md), and [vector-composition report](../../QA/tier3-validation-develop-20260926-vector-composition/report.md). The 2026-10-01 route-matrix continuation runs the `ISSUE-006`/`ROUTE-LIVE` rows and the EEA render retry (Acropolis, Open-Meteo aliases, generic-infrastructure clarification pass; the weather-forecast row passes at an adequate runtime budget; census demographics / numeric elevation / imagery extent remain `PARTIAL`; EEA is now routed through the same-origin AEGIS tile proxy but its render stays blocked by the retired `noise.discomap.eea.europa.eu` 2019 WMS). See the [route-matrix report](../../QA/tier3-validation-develop-20261001-route-matrix/report.md). Keep provider retrieval, routing, renderer loading, and acknowledgement as distinct boundaries. |
| Tier 4A | `T4-01`–`T4-08` | CSV/GeoJSON ingestion, optional heavy formats, mobility data, local/configured sources, cameras, credentialed providers, and catalog-only descriptors. | The [2026-10-01 T4A dataset-ingestion slice](../../QA/tier4a-dataset-ingestion-20261001/report.md) establishes the ID-to-scenario mapping and passes the deterministic isolated contract: `T4-01` CSV, `T4-02` GeoJSON, and `T4-08` catalog-only descriptors are `PASS`; `T4-03` optional heavy formats, `T4-04` mobility/GTFS, and `T4-05` local/configured sources are `PARTIAL` (optional deps not installed; no configured live feeds/datasets); `T4-06` cameras and `T4-07` credentialed providers are `BLOCKED` on missing configured sources/credentials. Run only with isolated data and approved credentials/snapshots. |
| Tier 4B | `T4-09`–`T4-13` | Exact OpenCode Go, OpenAI, Google, DeepSeek/OpenCode Zen, and Ollama parity. | Never substitute a provider or model; record unavailable lanes as blocked or unrun. |
| Tier 5 | `T5-01`–`T5-13` | Acknowledgement identity, failed-render recovery, races, outages, restart recovery, repetition, malformed input, cancellation, performance, accessibility, provider reconciliation, and hosted CI. | Requires the lower-tier contracts and exact-head evidence to be stable. |

The current roll-up is 40 `PASS`, 3 `PARTIAL`, 2 `BLOCKED`, and 23 `UNRUN`.

### Campaign inventory reconciliation

The 68 campaign slices are counted exactly once as follows:

| Status | Explicit slice IDs | Count |
| --- | --- | ---: |
| `PASS` | `T0-01`–`T0-05`, `T1-01`–`T1-12`, `T2-01`–`T2-07`, `T3-01`–`T3-10`, `T3-12`–`T3-14`, `T4-01`, `T4-02`, `T4-08` | 40 |
| `PARTIAL` | `T4-03`, `T4-04`, `T4-05` | 3 |
| `BLOCKED` | `T4-06`, `T4-07` | 2 |
| `UNRUN` | `T3-11`, `T3-15`–`T3-18`, `T4-09`–`T4-13`, `T5-01`–`T5-13` | 23 |

`T4-01`/`T4-02`/`T4-08` are `PASS` for the deterministic isolated fixture and
descriptor boundaries recorded in the [2026-10-01 T4A slice](../../QA/tier4a-dataset-ingestion-20261001/report.md).
`T4-03`/`T4-04`/`T4-05` are `PARTIAL` (optional `geospatial-ingestion`
dependencies are not installed; no configured live feeds or datasets),
and `T4-06`/`T4-07` are `BLOCKED` on missing configured camera sources and
approved credentials respectively. These classifications do not claim live
configured-source or credentialed-provider behavior.

`T3-15`–`T3-18` remain explicit `UNRUN` inventory entries (`T3-10`, `T3-12`,
`T3-13`, and `T3-14` are `PASS` per the [T3-10](../../QA/tier3-validation-develop-20261001-t3-10-t3-14/T3-10/report.md),
[T3-12](../../QA/tier3-validation-develop-20261001-t3-10-t3-14/T3-12/report.md),
[T3-13](../../QA/tier3-validation-develop-20261001-t3-10-t3-14/T3-13/report.md), and
[T3-14](../../QA/tier3-validation-develop-20261001-t3-10-t3-14/T3-14/report.md)
slices; `T3-11` remains unopened). Their individual
acceptance criteria were never preserved in the repository or its history
(verified against the campaign-creation commit `9c2da7a4` and the QA
consolidation `f3b819f2`); the reconstructed per-gate contracts are now
preserved in the
[Tier 3 rendering and feature families checklist](tier3_rendering_and_feature_families.md)
so they must not be re-inferred from the broad Tier 3 description. The grouped
Tier 4B (`T4-09`–`T4-13`) and Tier 5 (`T5-01`–`T5-13`) ranges are counted by
their declared cardinalities above; Tier 4B carries a one-lane-per-gate mapping
recoverable from this document, while Tier 5 has a 12-theme-to-13-gate
cardinality mismatch that must be resolved before execution.

The 2026-09-30 T3-07/T3-09 implementation follow-up centralizes public
raster browser transport at the manifest-backed AEGIS tile proxy, including
the native map-plan descriptor path. Local WMS, WMTS, XYZ, coordinate,
binary-payload, descriptor, and generic MapLibre consumer contracts pass. The
required exact `opencode-go / deepseek-v4.1-flash` browser lane produced a
visible attributed RainViewer raster over Naples with `render_observed=ready`.
The 2026-10-01 T3-07 follow-up closes the FEMA transport blocker: FEMA's
US-egress-restricted `hazards.fema.gov` is reached through FEMA's official
ArcGIS Online relay (the same relay FEMA's own NFHL Viewer uses), raster
results satisfy the `spatial_scope_applied` completion requirement, and
scale-dependent NFHL layer 28 is presented at a visible zoom. FEMA and ESA
public raster overlays now load through the same-origin AEGIS tile proxy and
render with accepted `map.render_ack` (`render_observed=ready`); `T3-07` is
`PASS`, `T3-08` remains `PASS`, and
`T3-09` is `PASS`: the exact Settings-API bootstrap persisted
`opencode-go / deepseek-v4.1-flash` in a fresh disposable runtime, the native
structured probe passed, and the subsequent browser run received an accepted visible-raster acknowledgement.
The 2026-10-01 route-matrix continuation adds `eea` to the proxied raster-provider
set and runs the `ISSUE-006`/`ROUTE-LIVE` rows: Acropolis, Open-Meteo aliases,
and generic-infrastructure clarification pass, and the weather-forecast row
passes at an adequate runtime budget (the default simple budget is a configuration
value); census demographics / numeric elevation / imagery extent
remain `PARTIAL`; EEA is proxied (same-origin) but its render stays blocked by
the retired `noise.discomap.eea.europa.eu` 2019 WMS. See the
[route-matrix report](../../QA/tier3-validation-develop-20261001-route-matrix/report.md).
The subsequent current-head contract follow-up at
`develop@889066b3` closes a repository defect where `tile`, `xyz`, `wms`, and
`wmts` raster candidates bypassed the visibility-proof requirement; the
2026-10-01 raster remediation additionally validates the acknowledged raster
semantics for FEMA and ESA. A bounded CSV/GeoJSON
ingestion fixture run was recorded as supporting evidence only until the
[2026-10-01 T4A slice](../../QA/tier4a-dataset-ingestion-20261001/report.md)
established the grouped Tier 4A ID-to-scenario mapping and opened `T4-01`–`T4-08`;
the durable production rollback/cleanup boundary remains an open validated
limitation (see the slice report).

The recommended execution order is numeric order within each tier. A blocked
credential or optional dataset slice may be deferred without stopping unrelated
slices. Conditional slices must state their prerequisite; for example, mixed
FEMA composition depends on a verified FEMA raster render.

## Slice execution contract

Every slice follows:

**Inspect -> Execute -> Observe -> Diagnose -> Surgically Fix -> Retest -> Record**

Before execution, record the branch, exact SHA, environment, provider/model
lane, and isolation boundary. On failure, reproduce once, identify the first
incorrect layer, read the concrete source path, make the smallest authorized
change, run the narrow regression, rerun the exact scenario, and update only
the affected ledger row. Validation work must not silently become remediation
work.

## Browser evidence package

Each browser slice should retain, where applicable:

`slice.json`, `browser.png`, `console.log`, `network-summary.json`,
`backend.log`, `run-trace.json`, `api-response.json`,
`database-observation.txt`, and `notes.md`.

Map slices additionally record conversation/run identity, requested and
resolved location, expected and actual bounds, basemap/source/layer IDs,
provider status, retrieved/rendered counts, `map.render_ack`, and attribution.
Never record credentials, secret-bearing payloads, private reasoning, or unsafe
raw provider responses. If the browser tool cannot export a local image, say
so explicitly rather than claiming a binary screenshot artifact exists.

## Completion rule

AEGIS must not receive a blanket comprehensive `PASS` until the exact tested
revision has no `FAIL`, `UNKNOWN`, or `UNTESTED` rows in Tier 0 or Tier 1,
proves the current migration and OpenAPI contract, passes the relevant local
quality/build gates, and completes the browser-authoritative core,
provider/render, recovery, and hosted-CI boundaries. `PARTIAL` and `BLOCKED`
remain visible until their stated gaps are closed or their product scope is
explicitly reclassified.

## Current campaign pointer

The first opened campaign slice is the T0-01 static-quality baseline at exact
`loop-dev` HEAD `5bb8d416da80e33a7e85b02538f605ee22aee0a5`. Its detailed
evidence is in
[`../../QA/t0-01-static-quality-20260922/report.md`](../../QA/t0-01-static-quality-20260922/report.md).
The Tier 1 application-foundations baseline remains recorded at
`loop-dev` SHA `c615c5799e1d5fb01e0af0eccaab5c6490d554c0`; its machine-readable
ledger and detailed evidence are in
[`../../QA/tier1-application-foundations-20260921/`](../../QA/tier1-application-foundations-20260921/).
The historical pointer below records the campaign's original opening counts (30 `PASS`, 0 `PARTIAL`, 0 `BLOCKED`, 38 `UNRUN`); they do not override the current ledger. The current roll-up is 40 `PASS`, 3 `PARTIAL`, 2 `BLOCKED`, and 23 `UNRUN`, across dated evidence boundaries that do not certify one common commit. Tier 0 is `PASS` for its functional Windows startup scope;
Tier 1 remains 12/12 `PASS`; the current Tier 2 ledger has seven `PASS` slices.
Preserve historical source boundaries in the linked T1 reports.

## Current Tier 0 execution record
The 2026-09-23 [T1-09 continuation](../../QA/tier1-validation-develop-20260923/T1-09/report.md)
passes Settings URL authority, all seven rendered sections, invalid-tab fallback,
draft retention, controlled save, and return/reopen. Its implementation commit
`c090abd1ca9d6d78e82e798da9167b9d19b3fc23` passed four jobs in [hosted CI run
35873578752](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35873578752).
The 2026-09-23 [T1-10 continuation](../../QA/tier1-validation-develop-20260923/T1-10/report.md)
passes credential lifecycle and Settings checks; Tier 1 remains 12/12 `PASS`, and
its implementation head passed four jobs in [hosted CI run
35891289442](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35891289442).
The previous T2 source-and-evidence head `3734df22a09eb83c279ac28467654c4cfa29bab6`
passed four jobs in [hosted CI run
35915263134](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35915263134).
The current continuation passes the Milan clarification/render and Rome-to-Florence
clarification/render scenarios plus the Zurich coverage guardrail. The T0/T2
follow-up now passes the bounded 50-candidate inventory after a temporary isolated
budget increase, with the original runtime setting restored; broader route, raster,
provider, and browser coverage remain open.

The pushed head `9b34c5aa52dd6c26c9c451d0d3384fa660e5893d` passed all four jobs
in [exact-head hosted CI run
36241506428](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36241506428).

The 2026-09-22 campaign continued on `develop` from starting SHA
`7e8b10d58aebf21f194a74bcc2307f9d8e08f15c`. All application data and pytest
state used isolated paths below `runtimes/cache/test-runtime` and
`runtimes/cache/pytest*`; the user's normal runtime database was not used by
the final validation and was verified restored to the documented provider
lane. The validated source was committed and pushed as
`afa608c8d5c53a34d0ce8da36e5fe5f47f689145`. The detailed reports are:

- [T0-03 legacy Settings migration](../../QA/tier0-validation-develop-20260922/T0-03/report.md)
- [T0-04 Windows startup](../../QA/tier0-validation-develop-20260922/T0-04/report.md)
- [T0-05 API composition](../../QA/tier0-validation-develop-20260922/T0-05/report.md)
- [final exact-head regression and reconciliation](../../QA/tier0-validation-develop-20260922/final/report.md)

The exact execution order was `T0-03 -> T0-04 -> T0-05 -> final T0-01/T0-02
regression sweep -> ledger reconciliation`. Local PASS does not promote the
hosted-CI, live-provider, complete browser matrix, or Tier 1 partial rows.
