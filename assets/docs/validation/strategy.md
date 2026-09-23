# Comprehensive validation strategy

Last updated: 2026-09-22

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
| Tier 0 | `T0-01`–`T0-05` | Static quality, current migration, legacy settings migration, Windows startup, and API composition. | [Current Tier 0 reconciliation](../../QA/tier0-validation-develop-20260922/final/report.md) records `T0-01` through `T0-05` as `PASS` on the same `develop` source boundary. |
| Tier 1 | `T1-01`–`T1-12` | Application foundations: routing, tab-local state, conversations, realtime, run lifecycle, HTTP chat, jobs, runtime Settings, credential lifecycle, model selection, and context presentation. | [Tier 1 checklist](tier1_application_foundations.md), [2026-09-23 T1-06 continuation](../../QA/tier1-validation-develop-20260923/T1-06/report.md), [T1-03 continuation](../../QA/tier1-validation-develop-20260923/T1-03/report.md), [2026-09-22 T1-02 continuation](../../QA/tier1-validation-develop-20260922/T1-02/report.md), and [2026-09-21 baseline](../../QA/tier1-application-foundations-20260921/report.md). T1-07 is next. |
| Tier 2 | `T2-01`–`T2-07` | Plain and ambiguous location flows, multi-turn replacement, landmarks, capability discovery, direct tools, history, and evidence inspection. | Open only after foundations are classified; preserve exact geography and no-fallback rules. |
| Tier 3 | `T3-01`–`T3-18` | Basemaps, vector/raster families, valid-empty behavior, public providers, overlay mutation, composition, and map inspection controls. | Keep provider retrieval, routing, renderer loading, and acknowledgement as distinct boundaries. |
| Tier 4A | `T4-01`–`T4-08` | CSV/GeoJSON ingestion, optional heavy formats, mobility data, local/configured sources, cameras, credentialed providers, and catalog-only descriptors. | Run only with isolated data and approved credentials/snapshots. |
| Tier 4B | `T4-09`–`T4-13` | Exact OpenCode Go, OpenAI, Google, DeepSeek/OpenCode Zen, and Ollama parity. | Never substitute a provider or model; record unavailable lanes as blocked or unrun. |
| Tier 5 | `T5-01`–`T5-13` | Acknowledgement identity, failed-render recovery, races, outages, restart recovery, repetition, malformed input, cancellation, performance, accessibility, provider reconciliation, and hosted CI. | Requires the lower-tier contracts and exact-head evidence to be stable. |

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
The latest per-slice roll-up remains `PARTIAL`: 14 slices are `PASS`, 3 are
`PARTIAL`, and 51 are `UNRUN`. These counts combine the cited dated evidence
boundaries; they do not certify one common commit. Tier 0 is complete. The
2026-09-22 continuation
records `T1-02` as `PASS` on the `develop` working tree based at
`8375fe071823e7f844f6bb125d86d6ebf36b3110`; its source changes were
fingerprinted in the [T1-02 report](../../QA/tier1-validation-develop-20260922/T1-02/report.md)
and later committed at `35d04f8399d0166d1a134ad9f45931bc15efda91`. Preserve
that historical test boundary. The 2026-09-23 [T1-03 continuation](../../QA/tier1-validation-develop-20260923/T1-03/report.md)
passes conversation search, paging, hydration, isolation, stale-ID recovery,
and a focused transcript-spacing repair. The [T1-06 continuation](../../QA/tier1-validation-develop-20260923/T1-06/report.md)
passes the exact-lane HTTP response matrix and corrected backend CI test
selection. Tier 1 is `PARTIAL` at 9 `PASS` and 3 `PARTIAL`; downstream
browser/provider/hosted-CI boundaries remain open. Continue at `T1-07`.

## Current Tier 0 execution record

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
