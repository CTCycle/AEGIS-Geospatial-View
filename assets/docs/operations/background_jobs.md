# Background Jobs

Last updated: 2026-06-07

## Scope

AEGIS uses one internal in-memory background job system for asynchronous chat and map work.

## Components

- `BackgroundJobService`
- `BackgroundJobWorker`
- `chat_turn` jobs
- `map_fetch` jobs

## Lifecycle

States:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`

Important fields include:

- `job_id`
- `job_type`
- `status`
- `progress_percent`
- `result_json`
- `error_json`
- `created_at`
- `started_at`
- `completed_at`
- `cancel_requested_at`

## API Surface

- `POST /api/chat/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/events`
- `POST /api/jobs/{job_id}/cancel`
- `POST /api/maps/jobs`
- `GET /api/maps/jobs/{job_id}`
- `DELETE /api/maps/jobs/{job_id}`

## Execution Model

- One worker thread claims queued jobs and dispatches by `job_type`.
- Chat jobs stream lifecycle events from the orchestrator into a shared event model.
- Map jobs execute the same location-search pipeline used by synchronous map requests.
- Missing-job failures are translated into HTTP 404 by the API layer.

## Cancellation And Constraints

- Cancellation is cooperative.
- `cancel_requested_at` is the single cancellation flag.
- Running handlers check cancellation between major execution phases.
- There is no force-kill mechanism for active work.
- Jobs are process-local and memory-backed.

## Configuration

- `jobs.polling_interval`
  Default poll interval returned to job clients.
