# Native Agent Validation Gate Ledger

Last updated: 2026-09-17 (rerun evidence at `12acd60381e75fee5fd6f93cb800218af3dc09bc`)

This is the canonical decision ledger for the native-agent loop, durable map
presentation lifecycle, browser fault harness, provider lanes, migrations, and
hosted CI. A gate is not complete until its exact evidence is linked or its
environment boundary is recorded. Statuses are limited to `PASS`, `PARTIAL`,
`FAIL`, `BLOCKED`, and `UNRUN`.

## Current ledger

| Gate / name | Subsystem | Lane / environment | Status | Verification date | Tested commit | Evidence link | Next action / boundary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ConversationState schema-v2 clarification projection and scope | Agent state | Focused native pytest plus isolated live API clarification checks | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [focused-native-final2.log](../../QA/native-agent-loop-evaluation-20260917-rerun/focused-native-final2.log) and [targeted clone clarification checks](../../QA/native-agent-loop-evaluation-20260917-rerun/live-orchestration-targeted-clone.log) | Keep `pending_clarification` as the sole durable/public contract; treat `unresolved_questions` as migration input only. Generic missing-location and ambiguous temporal requests both produced the scoped clarification/validation boundary. |
| Durable terminal presentation status | Run persistence | Backend unit and native orchestrator tests | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [backend-unit-final2.log](../../QA/native-agent-loop-evaluation-20260917-rerun/backend-unit-final2.log) | Preserve atomic closure for failed, cancelled, superseded, and timed-out render runs. |
| Tools-disabled finalization observability | Trace observability | Native agent loop focused tests | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [focused-native-final2.log](../../QA/native-agent-loop-evaluation-20260917-rerun/focused-native-final2.log) | Keep finalization traces sanitized: reason, model call index, `tools_exposed=0`, `tool_choice=none`, and no model content. |
| Controlled MapLibre happy path | Browser / MapLibre | Local Angular frontend plus backend, controlled WebSocket fixture | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [controlled completion report](../../QA/native-agent-loop-evaluation-20260917-rerun/browser-artifacts-final-clone/reports/controlled-map-completion.json) | Retain real `map.render_ack` gating and the rendered completion screenshot; this is controlled evidence, not hosted proof. |
| Controlled browser fault matrix: failed layer, viewport mismatch, stale/duplicate ack, cancellation, supersession, retry exhaustion | Browser / MapLibre fixture | Local Angular frontend plus backend; 8 scenarios | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [browser-fault-matrix-final-clone.log](../../QA/native-agent-loop-evaluation-20260917-rerun/browser-fault-matrix-final-clone.log) and [scenario reports](../../QA/native-agent-loop-evaluation-20260917-rerun/browser-artifacts-final-clone/reports/) | Keep injection after the real browser acknowledgment only; do not infer full live/hosted coverage from these 8 cases. |
| Exact configured provider structured readiness | Provider lane | `opencode-go / deepseek-v4.1-flash`; openai-chat-completions | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [provider-readiness-final-clone.json](../../QA/native-agent-loop-evaluation-20260917-rerun/provider-readiness-final-clone.json) | Preserve the exact configured lane; do not substitute another provider or model. |
| Live browser smoke | Browser / realtime | Exact configured lane; intentionally isolated `AEGIS_DATA_DIR=assets/QA/native-agent-loop-evaluation-20260917-rerun/live-runtime-data` | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [live-browser-final-clone.log](../../QA/native-agent-loop-evaluation-20260917-rerun/live-browser-final-clone.log) and [live artifacts](../../QA/native-agent-loop-evaluation-20260917-rerun/live-browser-artifacts-final-clone/) | Four smoke tests passed with real screenshots; the complete 22-scenario matrix remains outside this gate. |
| Live orchestration ambiguity smoke | API orchestration | Exact configured lane; intentionally isolated live API runtime | PARTIAL | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [live-orchestration-final-clone.log](../../QA/native-agent-loop-evaluation-20260917-rerun/live-orchestration-final-clone.log), [targeted clone clarification checks](../../QA/native-agent-loop-evaluation-20260917-rerun/live-orchestration-targeted-clone.log), [clone coordinate evidence](../../QA/native-agent-loop-evaluation-20260917-rerun/live-api-coordinate-final-clone.json), [clone trace](../../QA/native-agent-loop-evaluation-20260917-rerun/live-api-coordinate-trace-final-clone.json), and [historical timing evidence](../../QA/native-agent-loop-evaluation-20260917-rerun/live-orchestration-final2.log) | Targeted clarification checks passed for ambiguous temporal and missing-location requests (2 passed, 3 deselected). The clone coordinate request returned 409 while still running, then finalized durably; this is an async/timing boundary, not a routing regression. |
| Direct live coordinate completion | Agent runtime / geocode | Exact configured lane; intentionally isolated direct live API runtime | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [live-api-coordinate-final-clone.json](../../QA/native-agent-loop-evaluation-20260917-rerun/live-api-coordinate-final-clone.json) and [clone trace](../../QA/native-agent-loop-evaluation-20260917-rerun/live-api-coordinate-trace-final-clone.json) | Clone run `run_486d142dcf3744ce96e230de95918be4` completed through `place_search/geocode`; final text completion has `presentation_status=not_required`. |
| Alembic migration head and pending-operation check | Persistence schema | Isolated SQLite database | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [migration-check-final.log](../../QA/native-agent-loop-evaluation-20260917-rerun/migration-check-final.log) | Keep head `202609170001` and rerun against the isolated database when schema changes. |
| Focused native pytest | Backend / agent loop | Local Python environment; isolated writable basetemp | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [focused-native-final2.log](../../QA/native-agent-loop-evaluation-20260917-rerun/focused-native-final2.log) | 250 tests passed with one dependency warning; retain the focused boundary for reruns. |
| Backend unit suite | Backend | Local Python environment; isolated writable basetemp | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [backend-unit-final2.log](../../QA/native-agent-loop-evaluation-20260917-rerun/backend-unit-final2.log) | 820 tests passed with two dependency warnings; no full repository gate claim is made here. |
| Ruff lint | Python quality | Local repository, no-cache mode | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [ruff-final2.log](../../QA/native-agent-loop-evaluation-20260917-rerun/ruff-final2.log) | Keep protected-cache warnings separate from lint results. |
| Full strict Pyright | Static typing | Local `app/server/pyproject.toml` strict run | FAIL | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [pyright-final2.log](../../QA/native-agent-loop-evaluation-20260917-rerun/pyright-final2.log) | Resolve the unchanged repository baseline of exactly 47 errors, then rerun strict Pyright. |
| Frontend production build | Angular client | Local production build | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [frontend-build-final2.log](../../QA/native-agent-loop-evaluation-20260917-rerun/frontend-build-final2.log) | Keep generated `dist` output out of source control. |
| Frontend Karma tests | Angular client | Local ChromeHeadlessNoGpu | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [frontend-karma-final2.log](../../QA/native-agent-loop-evaluation-20260917-rerun/frontend-karma-final2.log) | 231 tests passed; rerun when client contracts change. |
| Synchronous `/api/chat/turn` terminal hydration | Backend API | Exact live provider lane; post-fix clone check | PARTIAL | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [live-api-coordinate-final-clone.json](../../QA/native-agent-loop-evaluation-20260917-rerun/live-api-coordinate-final-clone.json) and [clone trace](../../QA/native-agent-loop-evaluation-20260917-rerun/live-api-coordinate-trace-final-clone.json) | The clone request returned typed 409 while the run was still executing, then the durable run completed with `active_run=false` and `presentation_status=not_required`; retain the old 503 diagnostic as historical evidence only and separately investigate this async response boundary. |
| Full browser/API E2E matrix | Browser / API | Live services; subset only; final live runtime intentionally isolated | PARTIAL | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [live browser artifacts](../../QA/native-agent-loop-evaluation-20260917-rerun/live-browser-artifacts-final-clone/) and [controlled artifacts](../../QA/native-agent-loop-evaluation-20260917-rerun/browser-artifacts-final-clone/) | Controlled 8-scenario and live 4-test subsets passed; do not claim the complete 22-scenario matrix. |
| Complete 22-scenario live/hosted matrix | Coverage | Live provider plus hosted boundary | UNRUN | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [rerun final report](../../QA/native-agent-loop-evaluation-20260917-rerun/final-report.md) | Execute every required live and hosted scenario and capture exact lane, browser, API, persistence, and trace evidence. |
| Hosted CI at exact HEAD | Hosted CI | Remote workflow | UNRUN | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [rerun evidence index](../../QA/native-agent-loop-evaluation-20260917-rerun/evidence-index.md) | Run hosted CI for the exact SHA; no push or publish was performed in this rerun. |
| Harness process cleanup confirmation | Test harness | Local host; exact AEGIS services and test harness | PASS | 2026-09-17 | `12acd60381e75fee5fd6f93cb800218af3dc09bc` | [backend service log](../../QA/native-agent-loop-evaluation-20260917-rerun/backend-service-final-clone.stderr.log) and [rerun final report](../../QA/native-agent-loop-evaluation-20260917-rerun/final-report.md) | Known AEGIS backend/frontend processes were stopped; ports 7059, 4512, and 9876 and project test/browser/helper processes were verified absent. |

Final live/API evidence uses the intentionally isolated runtime above; backend
startup proof is [backend-service-final-clone.stderr.log](../../QA/native-agent-loop-evaluation-20260917-rerun/backend-service-final-clone.stderr.log).

## Browser fault acceptance contract

The controlled test may inject only WebSocket responses after the browser has
sent its real `map.render_ack`; it must not add production fault flags,
endpoints, catalog entries, or render-admission branches. Each controlled
scenario report records the run ID/version, candidate map session and revision,
complete sanitized acknowledgment payloads, bounded synthetic event sequence,
bounded final UI text, sanitized console errors/warnings, screenshot path, and
final presentation status.

- Failed layer and viewport mismatch require a failed observation, correction
  candidate, and eventual success or explicit retained last-known-good map.
- Stale or mismatched acknowledgment must be rejected and cannot commit the
  candidate.
- Duplicate acknowledgment must be idempotent.
- Cancellation and supersession must prevent old work from completing newer
  work.
- Retry exhaustion must be bounded and terminal, with no stale
  `presentation_status=pending` row.

## Update rule

Revise the smallest affected row when evidence changes. Keep `BLOCKED` and
`UNRUN` gates visible; do not convert local, controlled, or synthetic results
into live, provider, hosted-CI, or complete-matrix proof.
