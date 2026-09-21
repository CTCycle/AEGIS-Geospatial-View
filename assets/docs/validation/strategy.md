# Comprehensive validation strategy

Last updated: 2026-09-21

This document is the durable digest of the `loop-dev` comprehensive validation
roadmap. It defines the campaign order, evidence boundary, status vocabulary,
and hand-off points that future validation agents should use. The dated
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
| Tier 0 | `T0-01`–`T0-05` | Static quality, current migration, legacy settings migration, Windows startup, and API composition. | Reconcile current-HEAD environment and schema truth before broad functional claims. |
| Tier 1 | `T1-01`–`T1-12` | Application foundations: routing, tab-local state, conversations, realtime, run lifecycle, HTTP chat, jobs, runtime Settings, credential lifecycle, model selection, and context presentation. | [Tier 1 application-foundations checklist](tier1_application_foundations.md) and [2026-09-21 evidence](../../QA/tier1-application-foundations-20260921/report.md). |
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

The first opened campaign is the Tier 1 application-foundations baseline at
`loop-dev` SHA `c615c5799e1d5fb01e0af0eccaab5c6490d554c0`. Its machine-readable
ledger and detailed evidence are in
[`../../QA/tier1-application-foundations-20260921/`](../../QA/tier1-application-foundations-20260921/).
The current result is `PARTIAL`; this is intentional until the six partial
rows in that package are completed or explicitly reclassified.
