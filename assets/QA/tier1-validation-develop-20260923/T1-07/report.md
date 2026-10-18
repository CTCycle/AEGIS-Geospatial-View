# T1-07 Background Chat Jobs

Date: 2026-09-23
Slice result: `PASS`
Implementation commit: `develop@3fd0c820c2d4de0fb06120b6feac80b199d57f26`
Baseline: `develop@f5990c7c`

## Evidence boundary

The implementation commit contains the service, FastAPI lifespan, mounted API
coverage, and the updated operational contract. The exact source fingerprints
are in [source-sha256.txt](source-sha256.txt). The live request and restart
records use the isolated runtime at
`runtimes/cache/test-runtime/t1-07-live-20260923`; no default user data was
used.

## Controlled lifecycle and API

The standard Windows runner passed the focused job service and mounted API
suite: **11 passed**. It covers queue acceptance (`202`), successful worker
completion and terminal result, monotonically ordered events, stage/context
progress mapping, cooperative running cancellation, unknown-job `404` on
status/events/cancel, sanitized provider errors, and in-memory job reset across
service instances. The service shutdown case held an active streaming handler
for more than the former two-second join window; `stop()` remained blocked
until the handler reached its completion boundary and the worker thread exited.

The full backend unit run passed **918 tests**. It includes the app-factory
lifespan cleanup test and all job service/API tests. See
[backend-unit.log](backend-unit.log).

## Exact-lane live job

The official Windows launcher started the backend and frontend with isolated
runtime data. `/api/chat/settings` reported the configured
`opencode-go / deepseek-v4.1-flash` lane and healthy credential state. A real
`POST /api/chat/jobs` request returned `202`; the worker completed the job with
`status=succeeded`, `progress_percent=100`, operation success, and assistant
answer `4`. Event sequences 1–15 were ordered from `queued` through one
terminal `completed` event. No provider/model fallback occurred. See the
[redacted live-job record](live-job-evidence.json).

After restarting the official launcher against the same isolated runtime, the
new application was healthy and retained the same selected lane. The old
in-memory job ID returned `404` from status, events, and cancel routes. See
[restart evidence](restart-evidence.json).
The task-owned backend/frontend process tree was then stopped and verified
absent; ports 7059 and 4512 were no longer reachable.

## Quality gates

- Focused standard-runner service/API suite: **11 passed**.
- Full standard-runner backend unit suite: **918 passed**, including
  `test_stop_waits_for_active_job_and_joins_worker` and app-lifespan cleanup.
- Ruff: passed; three access-denied warnings came from pre-existing protected
  QA cache directories encountered during repository scan.
- Pyright strict project run: **0 errors, 0 warnings, 0 informations**.
- `git diff --check`: passed.

The full unit suite reported two known upstream deprecation warnings from
Google GenAI and Starlette/httpx. They did not affect the result.

## Hosted CI

The push-triggered `CI` workflow passed all four jobs against the exact
implementation commit `3fd0c820c2d4de0fb06120b6feac80b199d57f26`:
[GitHub Actions run 35861096479](https://github.com/CTCycle/AEGIS-Geospatial-View/actions/runs/35861096479).
See the [hosted-CI record](hosted-ci.md). The later evidence commit is
documentation-only and retains this tested implementation boundary.

## Operational boundary

The worker stops claiming new jobs and waits for active work to reach its
cooperative completion or cancellation boundary. There is no forced kill or
fixed shutdown timeout, so a provider call that never returns can delay app
shutdown. Job records are in-memory and are not restored after process restart.
