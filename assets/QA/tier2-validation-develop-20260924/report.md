# Validation recheck — 2026-09-24

## Scope and disposition

The next coherent work was to revisit the two open location workflow slices
(`T2-01`, `T2-02`) alongside the related controlled acknowledgement matrix
(`CONTROLLED-FAULT`). Current app source was checked against the prior T2
browser boundary (`develop@f6e78852b21e1c4abdcdded95148cf86ee9c3371`); no
production app source changed during this recheck.

| Item | Final status | Result |
| --- | --- | --- |
| `T2-01` location resolution | `PARTIAL` | Current focused backend coverage passed 86 tests. The live recheck could not start because the isolated runtime had no selected model and no OpenCode Go API key. Existing Milan candidate/label limitations remain. |
| `T2-02` hydrated and ambiguous location transitions | `PARTIAL` | Live recheck was blocked before a provider request. The existing ambiguity behavior remains unresolved: an ambiguous Florence follow-up can replace Rome without asking for confirmation. |
| Zurich FEMA coverage guardrail | `NOT RUN` | The live diary did not start; no Zurich coverage request was made in this recheck. The earlier guardrail evidence remains inconclusive. |
| `CONTROLLED-FAULT` | `PASS` | Full current browser module passed 10/10: visible map completion, eight controlled fault cases, and commit identity. This includes supersession, stale acknowledgement, and retry exhaustion. |

## T2 live recheck

The [official Windows launcher](official-launcher.log) started the app against
`runtimes/cache/test-runtime/tier2-validation-develop-20260924`. The Codex
in-app Settings screen showed **Agent model: Needs attention**, no selected
agent model, and **OpenCode Go API key: Not configured**. No provider query was
sent, and no fallback provider or model was used. The repository `settings/.env`
file was restored byte-for-byte; its restored SHA-256 is recorded in
[`t2-live-recheck.json`](t2-live-recheck.json). The isolated runtime and
scenario-by-scenario result are recorded in [`slice.json`](slice.json).

The 86 focused tests covering capability routing, location resolution, and the
agent loop passed. Their command result is in
[`focused-backend.log`](focused-backend.log). These tests do not substitute for
the blocked real-provider browser flows. The 2026-09-23
[T2 retry report](../tier2-validation-develop-20260923-retry/report.md) remains
the latest execution evidence for those live workflows and still supports only
`PARTIAL` for T2-01 and T2-02.

## Controlled browser acknowledgement matrix

The full command and result are in
[`controlled-fault/full-module.log`](controlled-fault/full-module.log):
`10 passed` in 18.91 seconds. The suite used the local Angular app and a
WebSocket fixture as its only fault injector; MapLibre generated the actual
browser acknowledgements. It covered the happy path plus failed layer,
viewport mismatch, stale acknowledgement, mismatched identity, duplicate
acknowledgement, cancellation, supersession, and retry exhaustion. The two
previously failing error cases now wait for their terminal acknowledgement
before checking the UI, and assert the run-error field separately from trace
status. A fixture response for an empty run trace prevents an unrelated
missing-conversation response from contaminating the screenshots.
The tested harness file SHA-256 is
`4DE5D6857B6796D807355E19CEDC56C086F97C0DEC7CDF86B4E34C10DF6982F2`.

The run-error cases displayed the appropriate error in the expanded execution
panel, removed the active Stop control, and did not display “Map ready.” The
screenshots and per-scenario JSON records are under
[`controlled-fault/screenshots/`](controlled-fault/screenshots/) and
[`controlled-fault/reports/`](controlled-fault/reports/). The pytest run emitted
one non-failing `PytestConfigWarning` because this repository configures
`cache_dir` while the cache plugin was disabled to avoid the protected shared
cache path. The happy path also recorded four repeated non-blocking WebGL
GPU-stall performance warnings; scenario reports contain no JavaScript console
errors.

This passes the controlled acknowledgement gate only. It does not prove live
FEMA or ESA raster loading, last-known-good retention with those public
overlays, or the complete provider/browser matrix. Those remain `PARTIAL` or
`BLOCKED` under `ISSUE-002`, `LIVE-HYD-20260920`, and `MATRIX-22`.

## Commit and hosted CI

The tested validation source/test commit is
[`a1b4e43ff20ab8683f34c04e9ff78e59dc01f74f`](https://github.com/CTCycle/AEGIS-Geospatial-View/commit/a1b4e43ff20ab8683f34c04e9ff78e59dc01f74f),
pushed to `origin/develop`. Its exact-head [GitHub Actions run
35970154295](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35970154295)
passed all four jobs: frontend build/tests, persistence conformance, backend
unit tests, and capability contract validation.

## Remaining validation boundaries

- `ROUTE-LIVE`, `LIVE-DIARY-20260919`, and `MATRIX-22` remain `PARTIAL`. The
  exact-lane location recheck was blocked, and broad routing, aliases,
  multilingual, coverage, and composition rows remain open.
- `LIVE-HYD-20260920` remains `PARTIAL`; FEMA/ESA MapLibre source loading is
  still unresolved and `GEO-HYD-05`/`GEO-HYD-06` remain `BLOCKED`.
- `runtime.startup.windows-local` remains `PARTIAL`; this official launcher
  pass confirms isolated startup health, while paired timing, provider-outage,
  and injected startup-failure checks remain open.
- `providers.normalized-adapters`, `maps.raster-overlays`, and
  `maps.state-preservation` remain `PARTIAL` because the controlled fixture
  does not establish live FEMA/ESA pixels, composition, or last-known-good
  retention with those public overlays (`ISSUE-002`).
- `ISSUE-006` remains open for RainViewer, EEA noise, PVGIS solar, Census, and
  some Open-Meteo aliases; these capability rows were not part of the live
  recheck. `ISSUE-001` remains resolved on the prior 2026-09-23 validation.
- Provider parity remains `BLOCKED` until its separate services and approved
  credentials are available. Credentialed/local source access also remains
  `BLOCKED`; dataset ingestion remains `UNVALIDATED`.
- `T2-04`–`T2-07` and Tier 3–5 remain `UNRUN`. The campaign roll-up remains 18
  `PASS`, 2 `PARTIAL`, 0 `BLOCKED`, and 48 `UNRUN` of 68 slices.
- `agent.map-render-ack-recovery` remains `PARTIAL` because the public raster
  source failure is independent of the now-passing controlled acknowledgement
  matrix.

The repository-level status is updated in
[`gate_status.md`](../../docs/validation/gate_status.md) and
[`project_status_ledger.md`](../../docs/project_status_ledger.md).

## Cleanup

The launcher-owned backend and frontend processes were stopped, task-created
browser tabs were closed, and ports 4512, 7059, and 9876 were verified free. The
isolated runtime data directory was removed and `settings/.env` retains its
recorded hash. Windows denied access to the task-created pytest scratch
directory `runtimes/cache/pytest-tmp/t2-location-20260924`, so that protected
temporary residue remains; it did not affect either test result.
