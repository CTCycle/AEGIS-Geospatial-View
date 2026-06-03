# Backend API

Last updated: 2026-06-02

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
  Starts asynchronous search and returns `JobStartResponse` with HTTP 202.
- `GET /api/maps/jobs/{job_id}`
  Returns `JobStatusResponse`.
- `DELETE /api/maps/jobs/{job_id}`
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
- `GET /api/geospatial/proxy/tomtom/{kind}/{z}/{x}/{y}.png`
  Proxies TomTom tiles.
- `GET /api/geospatial/cameras`
  Returns camera-network payloads.
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
- `POST /api/chat/stream`
  Streams NDJSON chat events.
- `GET /api/chat/models`
  Returns available cloud and local models.
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
- `POST /api/chat/vectors/rebuild`
  Rebuilds the vector index.
- `POST /api/chat/vectors/sync`
  Syncs vectors with manifests.
