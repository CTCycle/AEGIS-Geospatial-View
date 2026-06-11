# Backend API

Last updated: 2026-06-11

## Mounting

All routers are mounted with `/api` prefix in `app/server/app.py`.

## Search Routes

Defined in `app/server/api/search.py`:

- `GET /api/maps/catalog`
  Returns `GeospatialCatalogResponse`.
- `GET /api/maps/basemaps/osm/{z}/{x}/{y}.png`
  Proxies OSM basemap tiles.
- `POST /api/maps/search`
  Runs synchronous location search from `LocationSearchRequest` to `SearchByLocationResponse`.
- `POST /api/maps/jobs`
  Starts asynchronous map fetch and returns `JobStartResponse` with HTTP 202.
- `GET /api/maps/jobs/{job_id}`
  Wrapper around the canonical job status response.
- `DELETE /api/maps/jobs/{job_id}`
  Wrapper around the canonical cancel operation.

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
  Executes a chat turn and returns the structured result.
- `POST /api/chat/jobs`
  Starts an asynchronous chat turn and returns `BackgroundJobCreateResponse`.
- `POST /api/chat/stream`
  Streams NDJSON chat events.
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
- `session_id`
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

Notes:

- `assistant_delta` remains in the schema for forward compatibility, but current backend behavior does not emit fake token deltas.
- `final` carries the full serialized `ChatTurnResponse`, including `operation`.
