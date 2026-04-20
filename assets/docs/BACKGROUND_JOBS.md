# Background Job Management

Last updated: 2026-04-20
Scope: `AEGIS/server/services/jobs.py`, `AEGIS/server/services/search/composition.py`, `AEGIS/server/api/search.py`

AEGIS uses an in-process, thread-based job manager for asynchronous map-search execution.

## 1. Components

- `JobState` dataclass: per-job status container.
- `JobManager`: runtime-scoped coordinator for job lifecycle.
- `SearchRuntime.job_manager`: owner injected during app startup composition.

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

Exposed by map routes:
- `POST /api/maps/jobs`: start async map search
- `GET /api/maps/jobs/{job_id}`: fetch state snapshot
- `DELETE /api/maps/jobs/{job_id}`: request cancellation

Routes are mounted under `/api`.

## 4. Execution Model

- Each job runs in a dedicated daemon `threading.Thread`.
- Worker function for map jobs: `run_map_search_job(...)`.
- The runner updates progress and merges final result payloads.
- Failures are captured and surfaced through status polling.

## 5. Cancellation Semantics

Cancellation is cooperative:
- `cancel_job` sets `stop_requested=True` and marks status `cancelled`.
- Running logic must check `job_manager.should_stop(job_id)` and exit cleanly.
- There is no force-kill mechanism for active threads.

## 6. Operational Notes

- Jobs are process-local and memory-backed.
- Job state is not persisted across server restarts.
- Suitable for local and moderate concurrency scenarios.
- For distributed/high-volume workloads, migrate to external queue + worker infrastructure.
