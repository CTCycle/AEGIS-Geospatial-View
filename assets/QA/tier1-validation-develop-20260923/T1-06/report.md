# T1-06 validation report

Last updated: 2026-09-23

## Result

`PASS` for the five `/api/chat/turn` response boundaries: terminal `200`,
accepted `202`, genuine active-run `409`, missing-conversation `404`, and
unusable-provider `503`. The exact live lane was `cloud / opencode-go /
deepseek-v4.1-flash`; no provider fallback was used. The public response
contract and OpenAPI schema are unchanged.

## Source and environment boundary

- Branch: `develop`; starting commit: `4b5a6284379fd6f7fdcb2e523b2bde78e0387d87`.
- Implementation commit: `af663adaa5e14be3fcd7312e4bd230cca11f1b40`, pushed to `origin/develop` and passed exact-head hosted CI.
- Source changes tested: `.github/workflows/ci.yml`,
  `app/server/services/agent_runs/lifecycle.py`, and
  `app/tests/unit/api/test_chat_contracts.py`. Hashes are in
  [`source-sha256.txt`](source-sha256.txt).
- Runtime: official `start_on_windows.ps1 -Action Launch` workflow; API
  `127.0.0.1:7059`, client `127.0.0.1:4512`.
- Isolated live data: `runtimes/cache/test-runtime/t1-06-live-20260923`.
  A read-only check found zero synthetic conversation/run rows in the normal
  runtime database.
- Provider/model selection remained `cloud / opencode-go /
  deepseek-v4.1-flash`. The credential was temporarily deactivated only in the
  isolated runtime for the `503` case and restored active afterward.

## Live HTTP matrix

The sanitized matrix with request IDs, run identities, response details, and
database preflight/conflict checks is in
[`live-http-matrix.json`](live-http-matrix.json).

| Case | Result | Evidence boundary |
| --- | --- | --- |
| Terminal `200` | `PASS` | Exact provider/model run completed; assistant marker and provider/model context metadata were present. |
| Accepted `202` | `PASS` | Real HTTP route returned the durable run's `awaiting_render` state, pending presentation, matching run ID, status and realtime URLs, and `terminal=false`. |
| Genuine `409` | `PASS` | Second request arrived while the first run held the conversation; it returned the active-run conflict. The first run completed and only its one run row was persisted. |
| Missing `404` | `PASS` | Missing conversation returned before execution; isolated database had no conversation and no run for the supplied ID. |
| Unusable provider `503` | `PASS` | Temporarily inactive isolated credential produced only a bounded safe `detail`; provider/model selection and credential activation were restored. |

The `202` case used the repository's `create_or_get_run` and `prepare_render`
transitions to stage a durable run awaiting the normal browser render
acknowledgment. Its request used the real HTTP route and did not invoke the
provider. A preliminary attempt that held a run in `RUNNING` was correctly
claimed by the worker and completed with `200`; the final accepted case uses
the valid `AWAITING_RENDER` lifecycle state. That additional completed run was
confined to the isolated test database.

The live terminal case exposed a hydration defect: completed-event payloads
include run-level `state`, while serialization can omit the nullable
`context_usage.usage_percent`. Strict `ChatTurnResponse` validation then
discarded the valid terminal event and returned `503` after successful work.
Hydration now removes the event-only `state` and restores the omitted nullable
field before validation. A focused regression test covers both details. A
separate focused API test now covers the safe unusable-provider `503` boundary.

## Checks

| Check | Result | Detail |
| --- | --- | --- |
| `test_chat_contracts.py` and `test_openapi_schema.py` | `PASS` | 14 passed, 2 upstream deprecation warnings. |
| Corrected backend CI pytest selection | `PASS` | 397 passed, 2 upstream deprecation warnings; stale `app/tests/unit/services/search` target removed. |
| Ruff | `PASS` | All checks passed; Windows emitted three access-denied scan warnings for protected existing paths. |
| Pyright strict project | `PASS` | 0 errors, 0 warnings, 0 informations. |
| Python source compilation | `PASS` | 410 backend and test source files compiled. |
| Alembic | `PASS` | Isolated `upgrade head`, `check` reported no new operations, and `current --check-heads` reported `202609210001 (head)`. |
| Shared OpenAPI | `PASS` | Regenerated and `git diff --exit-code -- app/shared/openapi.json` remained clean locally and in hosted CI. |
| Hosted CI exact implementation head | `PASS` | Run 35845587545 on `af663adaa5e14be3fcd7312e4bd230cca11f1b40`; all four jobs passed. See [`hosted-ci.md`](hosted-ci.md). |

Full command output is retained in the adjacent `*-tests.log`, `ruff.log`,
`pyright.log`, `compile.log`, `alembic-check.log`, and OpenAPI logs.

## Gate roll-up and hand-off

T1-06 is `PASS`. Tier 1 is now `PARTIAL` at 9 `PASS` / 3 `PARTIAL`; the full
68-slice campaign is `PARTIAL` at 14 `PASS` / 3 `PARTIAL` / 51 `UNRUN`.
`ISSUE-003` is closed because the exact live response boundary passed. Continue
with `T1-07` background chat jobs. The separate hosted-CI gate also passed on
the exact pushed implementation commit; its job-level result is recorded in
[`hosted-ci.md`](hosted-ci.md).
