# Backend API

Last updated: 2026-09-15

## Mounting

All routers are mounted with `/api` prefix in `app/server/app.py`.

`GET /api/health` returns `{"status": "ok"}` for launcher readiness checks.
It is intentionally excluded from the generated OpenAPI schema.

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

Geospatial credential status and provider execution use the same
`GeospatialCredentialResolver`. It reads the active encrypted SQLite credential,
decrypts and validates it, and reports a saved but undecryptable credential as
unconfigured or as a structured credential-resolution error. There is no
environment-variable fallback.

## Chat And Model Routes

Defined in `app/server/api/chat.py`:

- `POST /api/chat/turn`
  Executes a chat turn and returns the structured result. `conversation_id` is required.
  This direct path retains its immediate response behavior; no second headless
  render-ack transport is provided for it.
- `POST /api/chat/jobs`
  Starts an asynchronous chat turn and returns `BackgroundJobCreateResponse`. `conversation_id` is required.
- `POST /api/chat/stream`
  Streams NDJSON chat events. `conversation_id` is required.
- `GET /api/chat/models`
  Returns available cloud and local models.
  Optional query: `provider=deepseek`, `provider=opencode`, or
  `provider=opencode-go` fetches the selected live catalog using the saved
  provider API key. The response includes per-source `ok`, reachability, error,
  and model-count status; a provider catalog failure is not converted into a
  usable empty catalog. `reachable` means catalogue transport success only;
  it is not inference or structured-output proof. Source statuses also expose
  the separate process-local structured-probe status and expiry timestamps.
- `GET /api/chat/models/structured-probe`
  Returns the latest selected-provider/model native structured-response probe, or `not_tested` when
  no unexpired result exists. Results are keyed by provider, model, protocol,
  base URL, and credential fingerprint and expire after 15 minutes.
- `POST /api/chat/models/structured-probe`
  Runs the selected model through the native route/tool contract using the
  fixed `Show a map of Italy` request. It stops before location resolution,
  provider execution, map assembly, and conversation persistence. A probe never
  changes model selection and never substitutes another provider or model.
- `GET /api/chat/settings`
  Reads persisted settings.
- `PATCH /api/chat/settings`
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
- `operation`
- `tool_payload`
- `map_session`
- `memory_snapshot`
- `context_usage`
- `execution_trace`
- `route`
- `goal`
- `completion_contract`
- `conversation_state`

`map_session.overlay_collection` is the required, revisioned authoritative
overlay collection. Its `instances` contain the render descriptor, stable
capability/scope/variant identity, visibility, opacity, and bounded
inspections. Render-entry arrays and separate overlay-ID projections are not
part of the map-session wire contract; clients derive those views from the
collection. The native `apply_map_plan` tool describes deterministic
add/remove/keep-only/show/hide/update operations against the revisioned
collection and returns the resulting map candidate. Browser render
acknowledgement is the only promotion path for a realtime map run.

Map-session inspections are carried by their owning overlay instance and may
represent feature, location, overlay, or non-spatial associations. Clients
should render only the normalized inspection contract and must not expose raw
provider metadata or unsafe links.

`operation` is the stable frontend-facing summary of verified backend outcome.

Supported `operation.kind` values:

- `map_session`
- `direct_answer`
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
- `context_usage`
- `stage`
- `final`
- `error`

`final` carries the full serialized `ChatTurnResponse`, including `operation`.

`POST /api/chat/turn` returns `503` when the selected provider credentials or
local provider configuration cannot be used. Dynamic model catalog requests
return `400` for an unsupported provider and `502` when the upstream catalog
cannot be loaded. Provider request failures are normalized into safe provider,
stage, code, HTTP-status, and retryability metadata without exposing response
bodies or credentials.

`POST /api/chat/turn` first checks that the conversation exists and returns
`404 Conversation not found.` without invoking the orchestrator when it does
not. Native runs start at the configured initial deadline and promote once to
the simple or complex profile after route validation. Traces contain bounded
stage observations, model/tool/transition counters, context usage, recovery,
and terminal reasons; prompts, credentials, and provider payloads are
excluded.

### Intentional limitation contract

- Antimeridian handling remains provider-dependent.
- Point or metadata-only weather sampling cannot claim an area overlay.
- Flood comparisons require verified comparable measures, units, and time
  windows; otherwise the existing clarification operation asks for separate
  layers or a comparable data contract.
- FIRMS and other provider credential failures remain structured limitations;
  provider fallback is not implied.
- Valid empty results are distinct from unavailable providers and produce an
  explicit no-results state.
- Browser acknowledgment is client-reported rendering evidence; backend
  semantic validation remains authoritative.

Native tool execution, evidence persistence, progress events, and final
response construction are owned by `NativeAgentOrchestrator`, `AgentLoop`,
and the typed tool registry/executor.

## Conversation Run Routes

Defined in `app/server/api/conversations.py`:

- `POST /api/conversations`
  Creates a durable conversation shell.
- `GET /api/conversations/{conversation_id}/realtime` (WebSocket)
  Opens the interactive `aegis.realtime.v1` protocol. The client sends
  `session.resume`, `run.start`, `run.steer`, and `run.cancel` envelopes; the
  server returns acknowledgements and ordered durable `run.event` envelopes.
  `client_request_id` and `client_mutation_id` make retries idempotent.
- `GET /api/realtime/metrics`
  Loopback-only JSON counters for active sockets, protocol errors, delivered
  events, and command latency. It is intentionally process-local in the
  supported single-replica deployment.

The v1 run stream emits concise user-visible events only: progress labels,
assistant text completion, request updates from steering, terminal errors,
completion, cancellation, and clarification-needed. Internal diagnostics can be
persisted with internal visibility and are not replayed on the normal user
stream.

Clarifications use the terminal `clarification_needed` event and may carry a
partial map session plus a visualization delta.
