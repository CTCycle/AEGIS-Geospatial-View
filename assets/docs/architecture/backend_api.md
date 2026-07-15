# Backend API

Last updated: 2026-07-14

## Mounting

All routers are mounted with `/api` prefix in `app/server/app.py`.

## Job Routes

Defined in `app/server/api/jobs.py`:

- `GET /api/jobs/{job_id}`
  Returns `BackgroundJobStatusResponse`.
- `GET /api/jobs/{job_id}/events`
  Returns `BackgroundJobEventsResponse`.
- `POST /api/jobs/{job_id}/cancel`
  Returns `JobCancelResponse`.

## Geospatial Routes

Defined in `app/server/api/geospatial.py`:

- `GET /api/geospatial/capabilities`
  Returns `GeospatialCatalogResponse`.
- `GET /api/geospatial/layers`
  Returns `GeospatialLayersResponse`.
- `GET /api/geospatial/layers/{layer_id}/health`
  Returns `GeospatialLayerHealthResponse`.
- `GET /api/geospatial/layers/{layer_id}/features`
  Returns `GeospatialProviderPayloadResponse`.
- `GET /api/geospatial/layers/{layer_id}/geojson`
  Returns raw GeoJSON `FeatureCollection` for map rendering.
- `GET /api/geospatial/providers/{provider_id}/layers`
  Returns normalized live provider-native layer descriptors. NASA GIBS uses WMS/WMTS XML capabilities and does not expose raw XML to the frontend.
- `GET /api/geospatial/providers/{provider_id}/layers/{layer_id}`
  Returns one normalized live provider layer descriptor with render metadata when available.
- `GET /api/geospatial/tiles/{capability_id}/{z}/{x}/{y}.png`
  Proxies manifest-backed raster tiles.
- `GET /api/geospatial/proxy/tomtom/{kind}/{z}/{x}/{y}.png`
  Proxies TomTom tiles.
- `GET /api/geospatial/cameras`
  Returns camera-network payloads.
- `GET /api/geospatial/cameras.geojson`
  Returns raw GeoJSON `FeatureCollection` for camera-point rendering.
- `GET /api/geospatial/cameras/{camera_id}`
  Returns `GeospatialCameraDetailResponse`.
- `GET /api/geospatial/sources/{provider_id}/credential-status`
  Returns `GeospatialCredentialStatusResponse`.
- `GET /api/geospatial/providers/account-setup`
  Returns provider account-setup metadata.
- `GET /api/geospatial/providers/{provider_id}/account-setup`
  Returns provider-specific account-setup metadata.
- `POST /api/geospatial/audit`
  Returns `LayerAuditReport`.

## Chat And Model Routes

Defined in `app/server/api/chat.py`:

- `POST /api/chat/turn`
  Executes a chat turn and returns the structured result. `conversation_id` is required.
- `POST /api/chat/jobs`
  Starts an asynchronous chat turn and returns `BackgroundJobCreateResponse`. `conversation_id` is required.
- `POST /api/chat/stream`
  Streams NDJSON chat events. `conversation_id` is required.
- `GET /api/chat/models`
  Returns available cloud and local models.
  Optional query: `provider=deepseek` to fetch the live DeepSeek model catalog using the saved DeepSeek API key.
- `GET /api/chat/settings`
  Reads persisted settings.
- `PUT /api/chat/settings`
  Updates settings and credentials.
- `POST /api/chat/models/ollama/refresh`
  Refreshes local Ollama models.
- `POST /api/chat/models/ollama/pull`
  Pulls an Ollama model.
- `GET /api/chat/models/ollama/health`
  Checks Ollama availability.

### Chat Turn Response

`POST /api/chat/turn` returns `ChatTurnResponse`.

High-level fields:

- `request_id`
- `conversation_id`
- `assistant_message`
- `turn_contract`
- `decision`
- `operation`
- `tool_payload`
- `map_session`
- `memory_snapshot`
- `context_usage`

`operation` is the stable frontend-facing summary of verified backend outcome.

Supported `operation.kind` values:

- `map_session`
- `direct_answer`
- `capability_catalog`
- `clarification`
- `rejection`
- `error`
- `failure_diagnostic`

Additional optional response fields:

- `task_snapshot`
- `tool_plan`
- `failure_diagnostic`
- `visualization_update`

Supported `operation.status` values:

- `success`
- `partial`
- `failed`

### Chat Stream Events

`POST /api/chat/stream` emits NDJSON `ChatStreamEvent` objects.

Current event sequence is lifecycle-oriented rather than token-oriented.

Supported event names:

- `status`
- `parsed`
- `policy`
- `tool_call_started`
- `tool_call_completed`
- `map_session_created`
- `final`
- `error`

`final` carries the full serialized `ChatTurnResponse`, including `operation`.

Planned tool execution, aggregation, synthesis, persistence, progress events,
and final response construction are owned by `PlannedTurnExecutionService`.

## Conversation Run Routes

Defined in `app/server/api/conversations.py`:

- `POST /api/conversations`
  Creates a durable conversation shell.
- `POST /api/conversations/{conversation_id}/runs`
  Creates one active agent run for the conversation and returns its SSE stream URL.
- `GET /api/conversations/{conversation_id}/runs/{run_id}/events`
  Streams durable user-visible run events as Server-Sent Events. Supports `after_event_id` and `Last-Event-ID` replay.
- `POST /api/conversations/{conversation_id}/runs/{run_id}/steering`
  Adds a steering message to the active run, rebuilds the deterministic aggregate request, and increments the run version.
- `POST /api/conversations/{conversation_id}/runs/{run_id}/cancel`
  Marks the active run cancelled as a terminal user action.

The v1 run stream emits concise user-visible events only: progress labels, assistant text completion, request updates, terminal errors, completion, and cancellation. Internal diagnostics can be persisted with internal visibility and are not replayed on the normal user stream.

Clarifications use the terminal `clarification_needed` event and may carry a
partial map session plus a visualization delta.
