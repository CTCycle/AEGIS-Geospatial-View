# Native Agent Validation Gate Ledger

Last updated: 2026-09-17

This is the canonical decision ledger for the native-agent loop, durable map
presentation lifecycle, browser fault harness, provider lanes, migrations, and
hosted CI. A gate is not complete until its exact evidence is linked or its
environment blocker is recorded. `PASS` means the stated path was exercised;
`PARTIAL` means only the listed subset passed; `FAIL` means the path ran and
violated its contract; `BLOCKED` means an external prerequisite was absent;
`NOT RUN` means no claim is made.

## Current ledger

| Gate | Status | Evidence / command | Boundary or next action |
| --- | --- | --- | --- |
| Conversation clarification migration and scope projection | PASS | Focused unit coverage in `app/tests/unit/domain/agent/test_conversation.py` | Legacy string questions migrate to schema v2; unrelated turns receive no blocking clarification context. |
| Terminal presentation status for failed/cancelled render runs | PASS | Focused repository/orchestrator tests in `app/tests/unit/services/test_agent_runs.py` and `test_agent_run_orchestrator.py` | Pending presentation is atomically closed as `failed`; render timeout remains `render_timeout`. |
| Tools-disabled finalization observability | PASS | `app/tests/unit/services/agent/test_agent_loop_v2.py::test_verified_render_emits_tools_disabled_finalization_trace` | Internal `finalization` trace records phase, reason, `tools_exposed=0`, and `tool_choice=none`; no model content is captured. |
| Controlled MapLibre happy path | PASS (prior evidence) | `assets/QA/native-agent-loop-evaluation-20260917/` and `app/tests/e2e/test_agentic_map_completion.py` | Retest after this slice when frontend/backend services are available. |
| Controlled browser fault matrix (failed layer, viewport mismatch, stale/duplicate ack, cancellation, supersession, retry exhaustion) | NOT RUN | Scenario injector is test-only in `app/tests/e2e/test_agentic_map_completion.py` | Run the parameterized Playwright test with real Angular/MapLibre; record each scenario's screenshot/report under `assets/QA/`. |
| Alembic migration head/check | PASS | Isolated SQLite `alembic upgrade head` followed by `alembic check` on 2026-09-17; head `202609170001` | The migration creates a schema-v2 clarification projection without dropping the legacy audit trail. |
| Focused backend tests | PASS | `53 passed, 2 warnings` on 2026-09-17 using the existing `app/server/.venv` | Includes conversation, loop finalization, run repository, and run orchestrator seams. |
| Frontend production build | NOT RUN in this slice | Existing build evidence remains in prior QA reports | Run `npm run build` after the browser harness is available. |
| Configured live provider completion | BLOCKED | Live credential/provider lane was unavailable in the 2026-09-17 evaluation | Re-run the exact configured model/provider; do not substitute a catalog or alternate provider. |
| Full browser/API E2E matrix | BLOCKED | Required backend services/ports were unavailable in the evaluation | Start the canonical services, then run the full matrix separately from controlled fixtures. |
| Hosted CI at exact HEAD | NOT RUN | No post-change hosted run | Push/CI ownership remains with the parent release workflow; record the exact SHA and job logs here. |

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
and unrun gates visible; do not convert a local synthetic result into live,
browser, provider, or hosted-CI proof.
