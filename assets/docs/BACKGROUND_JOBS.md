# Background Job Management

Last updated: 2026-03-28  
Scope: `AEGIS/server/services/jobs.py`, `AEGIS/server/api/search.py`

AEGIS uses an in-process, thread-based job manager for asynchronous map-search execution.

## 1. Components

- `JobState` dataclass: per-job status container.
- `JobManager`: singleton coordinator for job lifecycle.
- Shared instance: `job_manager`.

Location:
- `AEGIS/server/services/jobs.py`

## 2. Job Lifecycle

States:
- `pending`
- `running`
- `completed`
- `failed`
- `cancelled`

State fields include:
- `job_id`, `job_type`
- `status`, `progress`
- `result`, `error`
- `created_at`, `completed_at`
- `stop_requested`

## 3. API Endpoints

Exposed by `MapSearchEndpoint`:
- `POST /maps/jobs`: start async map search
- `GET /maps/jobs/{job_id}`: fetch state snapshot
- `DELETE /maps/jobs/{job_id}`: request cancellation

The same routes are mirrored under `/api`.

## 4. Execution Model

- Each job runs in a dedicated daemon `threading.Thread`.
- Worker function for map jobs: `run_map_search_job(...)`.
- The job runner updates progress and merges final result payloads.
- Failures are captured and truncated into `error` for status polling.

## 5. Cancellation Semantics

Cancellation is cooperative:
- `cancel_job` sets `stop_requested=True` and marks status `cancelled`.
- Running logic must check `job_manager.should_stop(job_id)` and exit cleanly.
- There is no force-kill mechanism for active threads.

## 6. Usage Pattern

Typical backend usage:
1. Validate request payload.
2. Start job with `job_manager.start_job(...)`.
3. Return `job_id` to caller.
4. Client polls job status endpoint.
5. Client reads `status` and `result` when `completed`.

## 7. Operational Notes

- Jobs are process-local and memory-backed.
- Job state is not persisted across server restarts.
- This model is appropriate for low/medium local concurrency and development workflows.
- For distributed/high-volume workloads, move to external queue + worker infrastructure.
