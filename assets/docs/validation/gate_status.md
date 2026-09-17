# Native Agent Validation Gate Ledger

Last updated: 2026-09-17 (reconciled at `05e5046d`)

This is the canonical decision ledger for the native-agent loop, durable map
presentation lifecycle, browser fault harness, provider lanes, migrations, and
hosted CI. A gate is not complete until its exact evidence is linked or its
environment blocker is recorded. `PASS` means the stated path was exercised;
`PARTIAL` means only the listed subset passed; `FAIL` means the path ran and
violated its contract; `BLOCKED` means an external prerequisite was absent;
`UNRUN` means no claim is made.

## Current ledger

| Gate | Status | Evidence / command | Boundary or next action |
| --- | --- | --- | --- |
| Conversation clarification migration and scope projection | PASS | Focused unit coverage in `app/tests/unit/domain/agent/test_conversation.py` | Legacy string questions migrate to schema v2; unrelated turns receive no blocking clarification context. |
| Terminal presentation status for failed/cancelled render runs | PASS | Focused repository/orchestrator tests in `app/tests/unit/services/test_agent_runs.py` and `test_agent_run_orchestrator.py` | Pending presentation is atomically closed as `failed`; render timeout remains `render_timeout`. |
| Tools-disabled finalization observability | PASS | `app/tests/unit/services/agent/test_agent_loop_v2.py::test_verified_render_emits_tools_disabled_finalization_trace` | Internal `finalization_started`/`finalization_completed` traces record reason, `model_call_index`, `tools_exposed=0`, and `tool_choice=none`; no model content is captured. |
| Controlled MapLibre happy path | UNRUN | Prior evidence remains in `assets/QA/native-agent-loop-evaluation-20260917/`; current collection is documented in `assets/QA/native-agent-loop-remediation-20260917/qa-reconciliation-addendum.md` | Relevant runtime code changed; rerun with the canonical Angular/backend services before restoring PASS. |
| Controlled browser fault matrix (failed layer, viewport mismatch, stale/duplicate ack, cancellation, supersession, retry exhaustion) | BLOCKED | Test-only fixture in `app/tests/e2e/test_agentic_map_completion.py` collects 8 tests; ports 8000 and 8001 were unavailable. See `assets/QA/native-agent-loop-remediation-20260917/qa-reconciliation-addendum.md`. | Start the canonical services and run the parameterized Playwright test; record each scenario's screenshot, acknowledgements, event sequence, and console output under `assets/QA/`. |
| Alembic migration head/check | PASS | Isolated SQLite `alembic upgrade head` followed by `alembic check` on 2026-09-17; head `202609170001` | The migration creates a schema-v2 clarification projection without dropping the legacy audit trail. |
| Focused backend/integration tests | PASS | Final integration run at `05e5046d`: `129 passed, 3 warnings`; full `app/tests/unit` run at the same revision: `809 passed, 3 warnings`. See `assets/QA/native-agent-loop-remediation-20260917/qa-reconciliation-addendum.md`. | Warnings are dependency deprecations and protected pytest-cache residue; rerun with a writable cache when ACL residue is cleared. |
| Ruff lint | PASS | `ruff check --no-cache app/server app/tests` at the final integration revision | Protected-cache access-denied warnings are environmental; rerun with a writable cache when ACL residue is cleared. |
| Full strict Pyright | FAIL | Repository-wide strict run at the final integration revision reported exactly `47 errors` (the changed clarification modules' targeted run is clean) | Resolve the repository baseline in provider Optional-access, maintenance-service, transport, and AgentLoop complexity diagnostics, then rerun `pyright --project app/server/pyproject.toml`. |
| Frontend production build | PASS | `npm run build` at the reconciled local revision completed in 17.043 seconds; see `assets/QA/native-agent-loop-remediation-20260917/qa-reconciliation-addendum.md`. | Keep build output out of source-control; browser/API proof remains separate. |
| Frontend Karma tests | PASS | `npm run test -- --watch=false --browsers=ChromeHeadlessNoGpu`: 228 successful tests; see `assets/QA/native-agent-loop-remediation-20260917/qa-reconciliation-addendum.md`. | Re-run if frontend contract or browser-harness changes land. |
| Configured live provider completion | BLOCKED | Live credential/provider lane was unavailable in the 2026-09-17 evaluation | Re-run the exact configured model/provider; do not substitute a catalog or alternate provider. |
| Full browser/API E2E matrix | BLOCKED | Required backend services/ports were unavailable in the evaluation | Start the canonical services, then run the full matrix separately from controlled fixtures. |
| Hosted CI at exact HEAD | UNRUN | No post-change hosted run | Push/CI ownership remains with the parent release workflow; record the exact SHA and job logs here. |

## Browser fault acceptance contract

The controlled test may inject only WebSocket responses after the browser has
sent its real `map.render_ack`; it must not add production fault flags,
endpoints, catalog entries, or render-admission branches. For each scenario,
the evidence must include run ID/version, map session ID, collection revision,
acknowledgment payload(s), final UI state, screenshot, and sanitized console
errors:

- failed layer and viewport mismatch: failed observation, correction candidate,
  and eventual success or explicit retained last-known-good map;
- stale or mismatched acknowledgment: rejection is visible and cannot commit
  the candidate;
- duplicate acknowledgment: idempotent completion with one committed map;
- cancellation and supersession: old work cannot complete the newer run;
- retry exhaustion: bounded attempts, terminal failure/status, and no stale
  `presentation_status=pending` row.

## Update rule

Append or revise the smallest affected row when evidence changes. Keep blocked
and `UNRUN` gates visible; do not convert a local synthetic result into live,
browser, provider, or hosted-CI proof.
