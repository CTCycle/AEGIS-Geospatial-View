# Comprehensive validation strategy

Last updated: 2026-09-25

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
| Tier 0 | `T0-01`–`T0-05` | Static quality, current migration, legacy settings migration, Windows startup, and API composition. | The [2026-09-22 Tier 0 reconciliation](../../QA/tier0-validation-develop-20260922/final/report.md) passed all five on its tested boundary. The [2026-09-25 T0/T2 follow-up](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md) revalidated the exact-head Windows launcher boundary: fresh/warm readiness, outage startup, ownership/PID-reuse safety, injected cleanup, canonical-state protection, and final port cleanup pass. `T0-04` remains `PARTIAL` only because a safe historical timing comparator is unavailable. |
| Tier 1 | `T1-01`–`T1-12` | Application foundations: routing, tab-local state, conversations, realtime, run lifecycle, HTTP chat, jobs, runtime Settings, credential lifecycle, model selection, and context presentation. | [Tier 1 checklist](tier1_application_foundations.md), [T1-10 continuation](../../QA/tier1-validation-develop-20260923/T1-10/report.md), [2026-09-23 T1-06 continuation](../../QA/tier1-validation-develop-20260923/T1-06/report.md), [T1-03 continuation](../../QA/tier1-validation-develop-20260923/T1-03/report.md), [2026-09-22 T1-02 continuation](../../QA/tier1-validation-develop-20260922/T1-02/report.md), and [2026-09-21 baseline](../../QA/tier1-application-foundations-20260921/report.md). Tier 1 remains 12/12 `PASS`. |
| Tier 2 | `T2-01` through `T2-07` | Plain and ambiguous location flows, multi-turn replacement, landmarks, capability discovery, direct tools, history, and evidence inspection. | The [2026-09-24 continuation](../../QA/tier2-validation-develop-20260924-head77c5d67/report.md) passes `T2-01`/`T2-02` on the exact OpenCode Go lane; `T2-03` remains `PASS`. The [2026-09-25 continuation](../../QA/tier2-validation-develop-20260925-next-slices/report.md) passes the tested `T2-05`/`T2-06`/`T2-07` scenarios, and the [T0/T2 follow-up](../../QA/tier0-tier2-validation-develop-20260925-t0-t2-followup/report.md) passes `T2-04` with five pages, 50 unique candidates, and `next_cursor=null` under an approved isolated six-call budget restored to four afterward. `ISSUE-001` is resolved. |
| Tier 3 | `T3-01`–`T3-18` | Basemaps, vector/raster families, valid-empty behavior, public providers, overlay mutation, composition, and map inspection controls. | Keep provider retrieval, routing, renderer loading, and acknowledgement as distinct boundaries. |
| Tier 4A | `T4-01`–`T4-08` | CSV/GeoJSON ingestion, optional heavy formats, mobility data, local/configured sources, cameras, credentialed providers, and catalog-only descriptors. | Run only with isolated data and approved credentials/snapshots. |
| Tier 4B | `T4-09`–`T4-13` | Exact OpenCode Go, OpenAI, Google, DeepSeek/OpenCode Zen, and Ollama parity. | Never substitute a provider or model; record unavailable lanes as blocked or unrun. |
| Tier 5 | `T5-01`–`T5-13` | Acknowledgement identity, failed-render recovery, races, outages, restart recovery, repetition, malformed input, cancellation, performance, accessibility, provider reconciliation, and hosted CI. | Requires the lower-tier contracts and exact-head evidence to be stable. |

The current roll-up is 23 `PASS`, 1 `PARTIAL`, 0 `BLOCKED`, and 44 `UNRUN`.

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
The latest per-slice roll-up is `PARTIAL`: 23 slices are `PASS`, 1 is
`PARTIAL`, and 44 are `UNRUN`. These counts combine the cited dated
evidence boundaries; they do not certify one common commit. Tier 0 is
`PARTIAL` for the broader Windows startup scope; Tier 1 remains 12/12
`PASS`; the current Tier 2 ledger has six `PASS` and one `PARTIAL` slice.
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
