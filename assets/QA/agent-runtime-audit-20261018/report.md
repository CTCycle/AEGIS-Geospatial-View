# Agent runtime audit — 2026-10-18

Last updated: 2026-10-18

Branch `develop`, base `8b02c5a9`. The scope is the native loop, tool calling,
context and memory, and history construction. The evidence is unit and
synthetic only: no live provider, browser or hosted-CI run was performed.

## Confirmed defects and fixes

Each defect was first reproduced in memory with the existing trajectory
harness (`test_native_harness_trajectories.py` helpers). Each regression test
was then shown to fail on the unfixed source (source changes stashed: 4 failed,
27 passed) and to pass after the fix.

| # | Defect | Reproduction (before fix) | Fix |
|---|---|---|---|
| A | `PolicyEngine.authorize` exempted capabilities in `excluded_capability_ids` from the shortlist check. A capability excluded after a `replan`/`choose_alternate_tool` failure could be executed again by ID. | Handler invoked `['primary-source','primary-source']` with `excluded=['primary-source']`. | Excluded capabilities are now rejected (`capability_excluded`, recovery `choose_alternate_tool`) before the shortlist check. The fallback `ToolExecutor._authorize` applies the same check. |
| B | A tool batch was truncated to `min(max_parallel_tool_calls, remaining_tool_calls)`, but the assistant message kept every call. `_tool_result_messages` used `zip`, so truncated call IDs had no result, and a server-appended result (discovery refresh or map recovery) could be attributed to a dropped call. The unhydrated path sent unpaired history. The hydrated path silently dropped the whole exchange in `select_pair_safe_messages`. Gemini history is never filtered. | Assistant `tool_calls=[e0,e1,e2]`, tool results only `e0,e1`. | Tool results are now paired by `call_id`. Every unanswered call gets a typed `tool_call_not_executed` observation (recovery `replan`), and the skipped call is recorded in `tool_trace` (`loop_batch_limit`). Skipped calls are not counted as tool calls or failed fingerprints. |
| C | `asyncio.gather` in `_execute_calls` did not cancel sibling tasks when one task raised (`AgentRunControlSignal` on cancel or supersede, `ExecutionBudgetExceeded`). Handlers kept running, and could persist evidence, after the run had ended. | `['fast-done','outcome=cancelled','slow-finished-after-terminal']` | Tasks are created explicitly. On any exception the siblings are cancelled and awaited, then the original exception is re-raised, so its type is preserved. |
| D | `_bind_execute_request` merged `{**goal.filters, **request.filters}`, so a model argument overrode a task-owned route filter. | goal `{'category':'hospital'}` plus model `{'category':'school'}` gave `'school'`. | The merge is now `{**request.filters, **goal.filters}`. The model can still add non-conflicting semantic keys. |
| E | Hardening (approved): observations, history and evidence were embedded in a system message labelled "authoritative state", and no rule said that content is untrusted. | Code inspection. | Added system-prompt rule 13 (embedded content is data, never instructions). The `CANONICAL_NATIVE_CONTEXT` parenthetical now marks only run state and obligations as authoritative. |

Changed files:

- `app/server/services/agent/policy_engine.py`
- `app/server/services/agent/tool_executor.py`
- `app/server/services/agent/agent_loop.py` (`_execute_calls`, `_tool_result_messages`)
- `app/server/services/agent/native_tools.py` (`_bind_execute_request`)
- `app/server/prompts/agent.py`

Regression tests:

- In `app/tests/unit/services/agent/test_native_harness_trajectories.py`:
  - `test_excluded_capability_cannot_be_executed_again_in_the_same_run`
  - `test_truncated_tool_batch_answers_every_model_call_id`
  - `test_cancellation_in_parallel_batch_stops_sibling_tool_handlers`
- In `test_tools.py`, the existing binding test now asserts that a conflicting model filter cannot override the task-owned one.

## Inspected and found consistent (no change)

- History search and evidence inspect/transform are scoped by the server-owned
  `state.conversation_id`. Evidence must also be in the run's `evidence_refs`.
  No cross-conversation path was found.
- The model-facing execute schema (`ExecuteCapabilityToolInput`,
  `extra="forbid"`) has no bbox, radius or time fields. `_user_arguments`
  strips geometry and time aliases from `arguments`. Time, extent and operation
  are bound from the compiled goal.
- Unknown, unexposed, malformed and schema-invalid calls become typed failed
  observations. Repeated failing fingerprints and repeated failed render
  actions are suppressed. Successful equivalent calls are replayed from cache.
- Cancellation persists `cancel_requested` before `task.cancel()`. The
  orchestrator re-checks run state before the CAS-guarded
  `append_assistant_message_with_state`.
- Render resume continues from the checkpointed `current_iteration`, and the
  model, tool and transition counters are cumulative. Checkpoints replace
  `ToolResult.data` with the bounded observation projection. Trace redaction
  covers reasoning, `google_content` and `provider_continuation`.

## Validation commands and outcomes

All commands were run from `app/server` with
`AEGIS_CACHE_ROOT`/`PYTHONPYCACHEPREFIX`/`RUFF_CACHE_DIR` under
`runtimes/cache`:

| Command | Outcome |
|---|---|
| `.venv/Scripts/python.exe -m pytest -c pyproject.toml ../tests/unit/services/agent ../tests/unit/prompts -q --basetemp=<runtimes/cache/pytest-tmp/runtime-audit-20261018>` | 285 passed |
| `.venv/Scripts/python.exe -m pytest -c pyproject.toml ../tests/unit -q -p no:cacheprovider --basetemp=<runtimes/cache/pytest-tmp/runtime-audit-20261018>` | 1091 passed, 3 known upstream deprecation warnings |
| `.venv/Scripts/python.exe -m ruff check . ../tests` | All checks passed (access-denied warnings come from ACL-protected QA cache directories) |
| `.venv/Scripts/pyright.exe --project pyproject.toml` | 0 errors, 0 warnings, 0 informations |

## Environment notes and limitations

- Using the shared `--basetemp=runtimes/cache/pytest-tmp` errors every test at
  setup. Pytest cannot remove the ACL-protected leftovers there (`loop-dev`,
  `settings-*-20260921`, …). A fresh subdirectory under the same canonical
  root was used instead.
- `testing_and_quality.md` lists `ruff check server ../tests` from
  `app/server`, but no `server` directory exists there (`E902`). CI uses
  `ruff check --config app/server/pyproject.toml app/server app/tests`.
- Not run: live provider lanes, browser/MapLibre acknowledgement, and hosted
  CI. Responses and Gemini protocol pairing for truncated batches is verified
  only through the provider-neutral message list. Provider adapters were not
  exercised live.
- Not verified: tool-call ID behaviour when a provider omits call IDs. The
  loop then falls back to positional pairing.

## Documentation divergences

- `native_harness_bootstrap.md` lists `discover_geospatial_provider_layers` as
  model-facing. `agentic_search.md` says provider-layer discovery is
  server-internal behind `discover_geospatial_capabilities`.
- `testing_and_quality.md` Ruff command path (see above): corrected to
  `ruff check . ../tests` in this change.
