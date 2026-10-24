# Native agent loop: high-priority remediation plan (H1 to H4)

Last updated: 2026-10-24

## Purpose and baseline

This is the implementation queue for the four **HIGH** findings in the AEGIS native-agent loop code audit. Each issue is a self-contained, copy-paste-ready implementation task; execute **H1, then H2, then H3, then H4**, testing and committing each independently on the branch `remediation/agent-loop-high-20261024`. The code inspected is `develop@dac3cc965149f216204d89fc1fdf94c9ab1514b3`. At plan creation no fixes or issue-specific test runs have been performed.

The findings are source-backed **failure risks**, not claims of reproduced production incidents. Existing validated workflows, provider selection, geospatial discovery, multi-target coverage, map rendering, vision policy, run budgets, and terminal response behavior must remain intact.

Tracking:
- [Native agent validation gate ledger](../validation/gate_status.md): supplemental `AL-H1` to `AL-H4`, currently `UNRUN`.
- [Project status ledger](../project_status_ledger.md): `ISSUE-007` and `agent.native-loop.high-reliability-edges` validation debt.
- [Existing native-harness plan](native_harness_bootstrap.md) and [testing standards](../coding/testing_and_quality.md).
- Historical Tier 0–5 `PASS` results remain historical evidence. These additional gates must not be counted as passed or alter campaign totals before verification.

## Universal implementation contract

For **each** task below:
1. Re-read the specified methods on the working branch and confirm the described risk still exists after preceding commits.
2. Make the smallest targeted production change. Reuse the current typed state, repository, tool registry and completion evaluator; do not add an external agent framework, worker, queue, or unneeded dependency.
3. Add deterministic regression tests for the edge case, adjacent happy path, state transitions and failure boundary. Do not simply assert a private helper's return value when the bug crosses components.
4. Run the focused suite and relevant existing backend quality gates. Report exact commands, results, and any unavailable validation.
5. Update the matching `AL-Hn` gate and `ISSUE-007` evidence with commit SHA and tested boundary. Mark `PASS` only after its acceptance criteria are demonstrated; otherwise use `PARTIAL`, `FAIL` or `BLOCKED` with a reason.
6. Commit changes on the remediation branch without merging, rewriting unrelated code, or altering existing gate history. Stop and document a material behavioral conflict before proceeding.

### H1. State-dependent capability discovery is incorrectly replayable

**Severity:** HIGH | **Gate:** `AL-H1` | **Estimated effort:** 0.5–1 developer day | **Order:** 1 of 4

**Confirmed code:** `app/server/services/agent/native_tools.py`, `discover_geospatial_capabilities` registration around lines 229–249, sets `idempotent=True`; `app/server/services/agent/agent_loop.py`, `AgentLoop._execute_calls` around lines 2165–2195 and 2270–2290, replays `successful_fingerprints` by tool name and arguments; `app/server/services/agent/tool_handlers/catalog.py`, `CatalogToolHandler.discover` around lines 121–167, filters `state.excluded_capability_ids` and updates `state.capability_ids`.

**Risk:** Repeating the same discovery arguments after excluding a failed provider/capability can replay the old successful shortlist. The cache fingerprint does not encode the changing exclusion state, so a stale shortlist may frustrate fallback/recovery.

**Standalone implementation prompt:**
> On AEGIS branch `remediation/agent-loop-high-20261024`, fix H1 only. Inspect discovery registration, cache lookup and exclusion mutation. Prefer the simplest correct fix: treat `discover_geospatial_capabilities` as state-dependent and ineligible for result replay. Ensure both regular model calls and server-side post-location refresh obtain a fresh shortlist when exclusions or route state change. Keep replay for genuinely stable tools and preserve tool budget/accounting, pagination and response schemas. Do not implement H2–H4.

**Acceptance tests:**
- Same discovery arguments before and after `excluded_capability_ids` changes return a refreshed list that omits the excluded ID; trace must not claim replay.
- If an alternative eligible source exists, discovery can expose it after provider/capability failure.
- Unchanged, genuinely cacheable tools still deduplicate; discovery pagination and `capability_ids` behavior remain valid.
- No infinite retry and no increase beyond established run/tool budgets.

**Expected benefit:** Reliable provider fallback and less confusing repeated discovery without introducing cache invalidation infrastructure.

### H2. Pending browser-render watchdogs are lost across process restarts

**Severity:** HIGH | **Gate:** `AL-H2` | **Estimated effort:** 1–2 developer days | **Order:** 2 of 4, after H1

**Confirmed code:** `app/server/services/agent_runs/render_completion.py`, `RenderCompletionService.prepare` and `_schedule_render_deadline` around lines 202–263, create `asyncio` tasks only in the current process; `app/server/services/agent_runs/lifecycle.py`, `RunLifecycleService.resume_active_runs` around lines 227–236, schedules only repository-listed runs; `app/server/repositories/agent_runs.py`, `AgentRunRepository.list_resumable_runs` around lines 292–318, includes pending/running/updating but not `awaiting_render`.

**Risk:** If the server stops with an acknowledged-to-be-rendered candidate still awaiting browser acknowledgement, the in-memory expiry task disappears. On startup the awaiting-render run is not rearmed, so a closed tab or absent acknowledgement may leave an active slot unresolved until another request/ack triggers inspection.

**Standalone implementation prompt:**
> On AEGIS branch `remediation/agent-loop-high-20261024`, fix H2 only, preserving H1. Add a narrow startup reconciliation path for persisted `awaiting_render` runs. Reuse the existing persisted presentation/preparation time and `expire_pending_render` behavior: expire overdue candidates immediately, rearm a single watchdog for unexpired candidates using **remaining** time, and leave already terminal or acknowledged runs unchanged. Keep version/conversation guards, event fanout and shutdown cancellation semantics. Do not rerun model inference for awaiting-render rows. Avoid polling daemons, new queues and database columns unless source inspection proves existing timestamp data insufficient. Do not implement H3–H4.

**Acceptance tests:**
- Persist awaiting-render run, emulate complete process/service restart, then verify the new service expires the candidate without a browser ack and releases/updates the run as designed.
- For a not-yet-expired candidate, preserve the original deadline; restart must not reset a full timeout.
- An acknowledgement before deadline wins; expired/already terminal candidates do not emit duplicate terminal events or watchdogs.
- Unrelated running/pending resumption, version guards, active-run ownership and graceful shutdown continue to work.

**Expected benefit:** Restart-safe browser handshake and no indefinitely stranded pending renders.

### H3. Bounded checkpoints can discard evidence required for correct completion

**Severity:** HIGH | **Gate:** `AL-H3` | **Estimated effort:** 2–3 developer days | **Order:** 3 of 4, after H1 and H2

**Confirmed code:** `app/server/domain/agent/capability_route.py`, `AgentRunState.checkpoint` around lines 536–561, persists only the last 16 `tool_results`; `app/server/services/agent/completion.py`, `CompletionEvaluator.data_checks` around lines 97–120 and `uncovered_data_obligations` / `uncovered_route_targets` around lines 360–414, evaluate prior results to prove requirements.

**Risk:** After enough tool executions, checkpoint/reload can remove earlier qualifying evidence. The resumed evaluator may consider previously covered queried metrics or geographic targets uncovered and repeat work, or make a different termination decision from the uninterrupted run.

**Standalone implementation prompt:**
> On AEGIS branch `remediation/agent-loop-high-20261024`, fix H3 only while preserving H1–H2. Inspect all completion and target-coverage consumers of `state.tool_results`. Introduce a **small, bounded, typed durable coverage summary** updated only after existing evidence eligibility checks pass, covering the minimum necessary fields such as validated capability IDs, covered queries and target references, plus any required scope assertions. Persist it in `AgentRunState.checkpoint` and hydrate it through existing checkpoint validation; keep the last 16 tool results as an observation/history window, not as the sole proof store. Prefer a shared projection/helper in the existing completion module to duplicating eligibility rules. Provide compatibility for old checkpoints that lack the summary. Avoid retaining full unbounded results or adding a generic event-sourcing system. Do not implement H4.

**Acceptance tests:**
- Execute enough interleaved tools to exceed the 16-result checkpoint window; compare pre/post-checkpoint `data_checks`, `uncovered_data_obligations`, `uncovered_route_targets`, and completion decisions for multi-location and multi-metric requests.
- Verified past evidence remains covered across restart; failed, spatially/temporally invalid, metadata-only, `not_found`, and analysis-ineligible evidence does not create false coverage.
- Old checkpoints hydrate without losing current behavior, and checkpoint JSON stays bounded as tool volume grows.
- New route/goal scope cannot inherit incompatible previous proof; current cancellation, budgets and final response work.

**Expected benefit:** Stable completion/termination decisions and reduced redundant provider calls after long runs and restarts.

### H4. Tool exposure disagrees with the canonical data-completion evaluator

**Severity:** HIGH | **Gate:** `AL-H4` | **Estimated effort:** 0.5–1 developer day | **Order:** 4 of 4, after H1–H3

**Confirmed code:** `app/server/services/agent/tool_registry.py`, `_data_obligation_unmet` around lines 421–449, considers success/partial outcomes from `execute_geospatial_capability`, `inspect_evidence`, or `transform_evidence` sufficient in its non-analysis branch; `app/server/services/agent/completion.py`, `CompletionEvaluator.data_checks` around lines 97–120, additionally requires eligible, valid evidence and satisfied target/data obligations.

**Risk:** An evidence inspection/transform can cause the capability-execution tool to disappear even when the canonical evaluator still marks `required_data_retrieved=False`. The model may be blocked from fetching needed data.

**Standalone implementation prompt:**
> On AEGIS branch `remediation/agent-loop-high-20261024`, fix H4 only while preserving H1–H3. Make the decision to expose `execute_geospatial_capability` consult the canonical validated data-completion state (including H3's durable coverage), rather than a divergent raw success test. Reuse `CompletionEvaluator` or a narrowly shared predicate; do not build another eligibility engine. Preserve route/domain/prerequisite exposure guards, explicit-capability constraints and valid-empty semantics. Inspection and transformation should not by themselves satisfy an unfulfilled provider-data requirement. Avoid introducing a dependency cycle. Do not alter independent non-data tasks or terminal response policy.

**Acceptance tests:**
- Successful `inspect_evidence` or `transform_evidence` without eligible provider data does not hide `execute_geospatial_capability` while `required_data_retrieved=False`.
- Ineligible/failed/metadata-only evidence cannot close the retrieval opportunity prematurely; valid qualifying provider data closes it according to existing policy.
- Analysis and multi-target/multi-metric routes honor uncovered obligations after the H3 checkpoint round trip.
- Existing exposure rules continue respecting routes, domains, budgets and terminal states.

**Expected benefit:** Tool availability agrees with the completion contract, preventing premature loss of a needed retrieval action.

## Order, checkpoints and closure

| Step | Gate | Dependency | Required evidence before next step |
| --- | --- | --- | --- |
| 1. Fresh discovery after exclusions | `AL-H1` | Current native loop | Regression showing failed-source fallback plus cache-control sanity |
| 2. Restart-safe render expiry | `AL-H2` | H1 retained | Persisted awaiting-render restart/timeout/ack race integration tests |
| 3. Durable completion proof | `AL-H3` | H1–H2 retained | >16-result checkpoint parity for eligibility, targets and obligations |
| 4. Canonical tool exposure | `AL-H4` | H1–H3 retained | Exposure-versus-completion agreement and no regressions |

Each gate is independently runnable, but the delivery sequence is fixed so H4 can reuse H3's durable coverage representation. All four start at **UNRUN**. Final closeout requires a focused end-to-end scenario involving provider fallback, multiple results/targets, checkpoint resume, map presentation and browser acknowledgement/timeout, plus the repository's applicable backend quality checks. Record exact branch head, test commands, failures and confidence limits in the canonical [gate ledger](../validation/gate_status.md). Do not overwrite older `PASS` results or imply CI/browser verification that has not occurred.
