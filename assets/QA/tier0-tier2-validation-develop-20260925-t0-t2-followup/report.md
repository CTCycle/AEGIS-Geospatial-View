# AEGIS T0-04 and T2-04 validation follow-up

- Date: 2026-09-25
- Branch: `develop`
- Tested source: `develop@800e0568f6b83254b60c4efe25e014e3fefdf81c`
- Evidence commit: `db5b9485e80073f87dd4a8b964e484ba42384fcb`
- Scope: `T0-04` Windows startup and `T2-04` capability inventory
- Final campaign roll-up: **23 PASS / 1 PARTIAL / 0 BLOCKED / 44 UNRUN**

## Result summary

| Slice | Final status | Evidence-backed conclusion |
| --- | --- | --- |
| `T0-04` | `PARTIAL` | Fresh and warm official-launcher readiness, simulated provider-outage startup, ownership/PID-reuse safety, injected backend/frontend readiness-failure cleanup, canonical-state protection, and final port cleanup pass. The sole remaining limitation is the unavailable safe historical before/after timing comparator; observed current timings are recorded in [`timing-results.md`](timing-results.md). |
| `T2-04` | `PASS` | The exact broad discovery request completed five browser-visible catalog pages (`12+12+12+12+2`), reconciled to 50 unique candidates and `next_cursor=null`, used six model calls under the temporary isolated budget, requested no map, and produced no `model_budget_exhausted` result. The original runtime setting was restored to 4 and verified after restart. |

## Validation performed

- Focused native/runtime/catalog suite: **83 passed**, 3 existing warnings. See
  [`focused-suite.log`](focused-suite.log).
- Startup/SQLite suite: **2 passed**, including
  `test_dynamic_provider_outage_does_not_block_isolated_application_startup`.
  See [`startup-checks.log`](startup-checks.log).
- Launcher safety harness: **PASS** for parse, unresolved-owner, noninteractive
  conflict, changed-owner/PID-reuse, synthetic termination refusal, and both
  injected readiness-failure cleanup paths. See
  [`launcher-safety-harness.json`](launcher-safety-harness.json).
- Official launcher readiness: four isolated successful starts with current
  timing samples. See [`timing-results.md`](timing-results.md) and the launcher
  logs.
- Browser-visible exact lane, settings mutation/restoration, inventory trace,
  empty map boundary, and final native model probe: see
  [`browser-evidence.md`](browser-evidence.md) and
  [`inventory-run-trace.json`](inventory-run-trace.json).
- Exact pushed-head GitHub Actions run
  [36152093449](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/36152093449)
  passed all four jobs. The pushed evidence commit contains documentation and
  QA artifacts only; the implementation source tested above remains
  `800e0568f6b83254b60c4efe25e014e3fefdf81c`. See
  [`hosted-ci-followup.md`](hosted-ci-followup.md).

## Remaining boundaries

`T0-04` remains `PARTIAL` only because a safe paired historical timing
comparator could not be reproduced. This does not promote the broader startup
performance claim.

The broader route matrix, raster/state-preservation gaps, provider parity,
credentialed/local-source access, dataset ingestion, and Tier 3–5 campaign rows
remain explicitly partial, blocked, unvalidated, or unrun as recorded in the
canonical ledgers. This follow-up does not claim provider parity, raster pixels,
dataset ingestion, or completion of any Tier 3–5 slice.

No source or test implementation change was required by the live validation.
The evidence package contains sanitized metadata only; it contains no
credentials, private reasoning, or raw provider payloads.
