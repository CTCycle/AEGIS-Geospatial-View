# Background Jobs

Last updated: 2026-06-06

## Scope

AEGIS uses a pluggable job backend contract for asynchronous map-search execution.
The default implementation remains an in-process, thread-based backend.

## Components

- `JobState`
- `JobBackend`
- `InProcessJobBackend`
- `SearchRuntime.job_manager`

## Lifecycle

States:

- `pending`
- `running`
- `completed`
- `failed`
- `cancelled`

Important fields include:

- `job_id`
- `job_type`
- `status`
- `progress`
- `result`
- `error`
- `created_at`
- `completed_at`
- `stop_requested`

## API Surface

- `POST /api/maps/jobs`
- `GET /api/maps/jobs/{job_id}`
- `DELETE /api/maps/jobs/{job_id}`

## Execution Model

- Each job runs in a dedicated daemon thread.
- `InProcessJobBackend` is the current concrete implementation.
- Map-search jobs execute through `app/server/services/search/execution.py::run_search_job(...)`.
- Missing-job and initialization failures are translated into HTTP errors by the API layer.
- Failures are surfaced through status polling.

## Cancellation And Constraints

- Cancellation is cooperative.
- `cancel_job` sets `stop_requested=True`.
- Running logic must check `job_manager.should_stop(job_id)`.
- There is no force-kill mechanism for active threads.
- Jobs are process-local and memory-backed.
- Future durable backends such as Redis/RQ, Celery, or Arq are not implemented yet.

## Configuration

- `jobs.backend`
  Current supported value: `in_process`
- `jobs.require_durable_backend`
  When `true`, startup rejects the `in_process` backend.
