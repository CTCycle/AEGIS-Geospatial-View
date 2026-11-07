# Post-R12 audit remediation (2026-11-07)

Baseline: `develop@82556e6e`, R12 live suite ([after-r7.md](../agent-loop-reliability-20261105/after-r7.md)) and the architectural audit (verdict PARTIAL, retain architecture). Unit-verified only; **no live re-run**.

## Changes

1. **Country framing.** `map_session_builder._country_main_landmass_bbox`: the viewport of a `country` location covers only shape parts at least 0.25 times the largest part's area. This drops Azores, Madeira, Canaries and French Guiana, and keeps Alaska. The location bbox used for data queries is unchanged.
2. **Finalization cost** (S12-T4, recorded run `run_2e0f0aec…`).
   - **Trace finding.** Call 3 is a text stop that is correctly corrected toward `transform_evidence`. Call 5 is a full synthesis that restates the answer the model already wrote at call 3.
   - **Fix.** That held-back answer (`AgentRunState.deferred_answer`) is reused at finalization when only derivation tools ran since, a met analysis obligation has cite groups, and the answer check passes. Expected effect: −1 call and about −13k tokens.
   - **Correction cap.** At most one targeted correction is allowed when held evidence plus an exposed derivation tool can close every pending requirement. After that the run finalizes deterministically.
   - **Per-phase tokens.** Model calls are tagged `call_phase` (routing / execution / finalization), and `ContextUsageResponse.phases` is now filled.
   - **Not changed.** S09-T2 is unchanged: its cost is context growth (prior-turn hourly forecasts plus describe payloads), and the next lever is trimming the context assembler.
3. **S16-T2.**
   - The map-state summary names the framed place when the request asked for it.
   - `layer_edit_count` no longer reads 0 after the render commit, which had caused a false "claims a layer was changed" rejection. `map_plan_service` now records `layer_edits` when the plan is prepared.
4. **Durable ledger continuity.**
   - **New statuses.** `ConversationTaskStatus` gains `blocked` (with a bounded `reason`: the stop reason, `evidence_unsupported` or `unmet`) and `superseded`.
   - **Ledger outcomes.** Unmet obligations are recorded as blocked instead of being dropped.
   - **Merging.** `merge_ledger` marks unfinished work from earlier requests as superseded when later work takes it over. A completed entry is never erased by a failed or blocked attempt.
   - **Eviction order.** Superseded entries go first, then completed, then the oldest.
   - **Projection.** `ledger_view` also projects up to 4 unfinished entries from earlier requests.
   - **Reuse.** Reuse authority (`compatible_tasks`) is unchanged.
   - `app/shared/openapi.json` was regenerated for the new status values and the `reason` field.

## Validation

- Full unit suite, run from `app/`: 1624 passed, 3 failed ([full-unit.txt](full-unit.txt)). The failures are not caused by this change.
  - `test_launcher_cleanup` already failed before this work.
  - The two `test_credential_and_evidence_storage` async tests fail with "async def functions are not natively supported" depending on the selection or order of tests. They pass when run with the API contract tests. Their code is untouched.
- Focused outputs: [framing-unit.txt](framing-unit.txt), [finalization-unit.txt](finalization-unit.txt), [ledger-unit.txt](ledger-unit.txt). Ruff is clean, and strict pyright reports 0 errors on the changed server files (as reported per change).

## Follow-up batch (same day)

1. **One-correction cap test.** The new test is `test_failed_derivation_after_the_targeted_correction_does_not_earn_a_second_one`.
   - **Trajectory:** the model text-stops, receives one correction, runs a failing `transform_evidence`, then text-stops again.
   - **Assertions:** the failed transform widens the pending set; exactly one correction is given; the run makes 4 model calls and ends `insufficient_evidence`.
   - **Mutation check:** with the cap disabled the test fails (`2 == 1`).
2. **Route prompt note: dropped.**
   - **Problem:** a one-line rule about the ledger statuses pushed the `nested_arguments_regression` trajectory gate over its token budget (14,376 > 13,669 × 1.05). The route prompt is re-sent on every call in that scenario.
   - **Decision:** the projected entries already carry self-describing `status` and `reason` values, so the prompt is unchanged.
3. **Model 429 honours `Retry-After`.**
   - **Error capture:** `LLMProviderRequestError.retry_after_seconds` is read from the provider response for retryable errors. `parse_retry_after` moved to `server/common/time.py` and is shared with the geospatial providers.
   - **Wait rule:** the agent-loop retry waits `max(backoff, min(Retry-After, 20 s))`.
   - **Budget:** if that wait exceeds the run budget, the loop raises at once instead of sleeping. The SDK adapters already have `max_retries=0`, so the loop is the only retry path.
4. **Client WebSocket close codes.**
   - **Bug:** browsers only allow client close codes 1000 and 3000–4999. `realtime.service.ts` called `close(1013, 'command_ack_timeout')` and `close(1002, 'invalid_server_message')`, which threw `InvalidAccessError` instead of closing. So the command-ack-timeout recovery could never reconnect.
   - **Fix:** the codes are now 4013 (retryable) and 4002 (terminal, added to the non-retry list).
   - **Tests:** the spec's fake socket enforces the browser rule, and a new spec covers ack-timeout → reconnect → command resent. 9/9 pass.

## Live recovery checks (2026-11-07)

Backend `server.app:app` on 7059, `ng serve` on 4512, built-in browser, OpenCode Go / DeepSeek v4.1 Flash. Metrics are in [live-runs.txt](live-runs.txt), produced by [run_metrics.py](run_metrics.py).

| Check | Setup | Result |
| --- | --- | --- |
| Model 429, before the Retry-After fix | [fault_proxy.py](fault_proxy.py) answers the first 2 model POSTs with 429 `Retry-After: 2` and forwards the rest to opencode.ai. [backend_via_proxy.py](backend_via_proxy.py) points only the in-process OpenCode Go base URL at it. | **PASS.** Run `805ff2`: 2 retries, then the 3rd attempt succeeded and the run completed with a correct answer. The trace shows the retries ignored Retry-After (about 0.25 s apart), which led to fix 3. |
| Model 429, after the fix | Same setup. | Run `19abac` waited out each Retry-After (deadline went 296.9 → 294.9 → 290.1 s). The 3rd attempt reached the real provider, which itself returned **429** (the provider was throttling at the time; model calls were already taking 30–60 s). After 3 attempts the run failed honestly: "model provider … transient error (provider_rate_limited) … retries did not recover". There was no false success. |
| WS reconnect + replay | Mid-run (S09-T1 prompt), the realtime socket was closed from the page with 4013. Browsers cannot send 1013; 4013 drives the same client reconnect-and-replay path as a server 1013. | **PASS.** Run `900900`: the client reconnected in 0.33 s with `session.resumed`. The client received exactly the server's user-visible sequences (1, 7, 9 … 35, …), with no gap or duplicate; 2–6 are `internal`. The run completed with the correct three-city answer. |

A server-originated 1013 (`event_replay_required` / `outbound_backpressure`) was not forced live. It needs backend fault injection; the client reconnect path it triggers is the one exercised above.

## Full suite: not re-run

The built-in browser pane was hidden and this session was not open in a window, so the page drew 0 animation frames and MapLibre could not render. S02 (`cdc4b6`) stuck in `awaiting_render` after 3 map attempts and 74.7k tokens. That is an environment artifact, not a verdict. S01 completed normally (5 calls, 20.4k tokens, the same as r7; 206 s because of provider latency). Together with the provider's live throttling, the frozen 16-scenario suite could not be judged fairly today.

## Validation (after the follow-up batch)

- Full unit suite: 1627 passed, 4 failed before the prompt revert. The `nested_arguments_regression` gate passes after the revert. Agent, domain and benchmark subsets: 715 passed.
- The remaining failures do not come from this batch: `test_launcher_cleanup` was already failing, and the two order-dependent async evidence-storage tests fail with "async def functions are not natively supported".

## Rate-limit backoff (after the r8 partial suite)

The r8 run hit real provider throttling on 7 of 18 turns. Each time, three attempts spread over about 10 s were not enough.

- **Change (`LLMTransportPolicy`).** A `provider_rate_limited` call now follows its own schedule: up to 6 attempts with waits of 2, 4, 8, 16 and 16 s (about 46 s in total).
  - New settings: `rate_limit_max_attempts`, `rate_limit_backoff_base_seconds` and `rate_limit_backoff_max_seconds`.
  - The provider's Retry-After still raises any wait, capped at 20 s.
  - Every wait is still bounded by the run budget.
  - Other retryable errors keep the short schedule (2–3 attempts).
- **Code.** `attempts_for(rate_limited=...)` and `retry_delay(..., rate_limited=...)` in `services/llm/transport.py`; the agent loop uses `_model_attempt_limit`.
- **Unit test.** `test_model_retry_honors_provider_retry_after_within_budget` covers sustained throttling: 4 failures, waits of 2, 4, 8 and 16 s, success on the 5th attempt, past the generic attempt limit of 2. Agent, LLM, benchmark and domain tests: 826 passed. Ruff is clean; pyright reports 0 errors.
- **Live check.** The fault proxy injected 4 consecutive 429s into the real lane. Run `a9fb72` recovered and completed: the haiku was answered after the 5th POST. Under the old policy it would have failed after the 3rd.

## Still open

- Full 16-scenario live re-run with the Browser pane visible and the provider not throttling.
- Server-forced WS 1013 live.
- A render that never acknowledges (as in a hidden pane) cost 7 execution calls and about 71k tokens before the backend was stopped; look at whether the render retries should stop sooner.
- S09-T2 context size; S07 does not explain the impossible magnitude; S06 uses two Open-Meteo capabilities.
