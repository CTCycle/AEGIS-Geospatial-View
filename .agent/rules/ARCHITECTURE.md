# AEGIS Geospatial View Architecture

## 1. High-Level Architecture Overview

### 1.1 Purpose and Scope
AEGIS Geospatial View converts free-text locations or explicit coordinates into normalized bounding boxes and map previews. The system focuses on geocoding, selecting NASA GIBS satellite layers, rendering overlays, and presenting results in a web UI. It also provides a lightweight database browser for stored metadata and search history.

### 1.2 System Overview
- Frontend components: React + Vite UI with a geospatial search page, agentic settings panel, map preview, metrics panel, and a database browser.
- Backend services: FastAPI app with map search and database browser routes, geospatial services (Nominatim, GIBS, OpenAQ, Open-Elevation), Folium map rendering, and persistence for layer metadata and search sessions.
- External dependencies and integrations: OpenStreetMap Nominatim, NASA GIBS WMS/WMTS endpoints, OpenAQ API, Open-Elevation API, Folium tile providers, SQLite/Postgres via SQLAlchemy, Pillow for imagery handling.

### 1.3 Deployment and Runtime Assumptions
- Backend targets Python 3.12; frontend targets Node 18+ (Windows launcher installs Node 22 and Python 3.12 in `AEGIS/resources/runtimes`).
- Default ports: FastAPI `127.0.0.1:8000`, Vite preview `127.0.0.1:7861` (manual dev server uses 5173).
- Vite proxies `/api/*` to the FastAPI host/port; frontend can override with `VITE_API_BASE_URL`.
- Backend configuration is driven by `AEGIS/settings/configurations.json` and optional `AEGIS/settings/.env` (template in `AEGIS/resources/templates/.env`).
- Embedded database uses SQLite at `AEGIS/resources/database/sqlite.db` unless external Postgres is enabled.
- Logs are written to `AEGIS/resources/logs`.

---

## 2. Codebase Structure

### 2.1 Directory Layout

| Path | Description |
|-----|-------------|
| `/AEGIS` | Application root (frontend, backend, resources, scripts) |
| `/AEGIS/client` | React + Vite frontend |
| `/AEGIS/server` | FastAPI backend (routes, schemas, services) |
| `/AEGIS/server/utils` | Configuration, constants, logger, and service helpers |
| `/AEGIS/server/database` | Database backends and ORM schema |
| `/AEGIS/server/scripts` | Maintenance scripts (DB init, layer sync) |
| `/AEGIS/settings` | Server configuration and environment overrides |
| `/AEGIS/resources` | Runtime assets (database, logs, templates, runtimes) |
| `/AEGIS/assets` | Static assets |
| `/docs` | Documentation |

### 2.2 Key Modules
- Backend entrypoint and routing: `AEGIS/server/app.py`, `AEGIS/server/routes/search.py`, `AEGIS/server/routes/browser.py`.
- Schemas and validation: `AEGIS/server/schemas/geographics.py`.
- Geospatial services: `AEGIS/server/utils/services/geospatial/*` (GIBS, Nominatim, OpenAQ, Open-Elevation, MapService).
- Data persistence: `AEGIS/server/database/*`, `AEGIS/server/utils/repository/serializer.py`.
- Configuration and constants: `AEGIS/server/utils/configurations/server.py`, `AEGIS/server/utils/constants.py`.
- Frontend pages and components: `AEGIS/client/src/pages/*`, `AEGIS/client/src/components/*`.
- Frontend API client and state: `AEGIS/client/src/services/api.ts`, `AEGIS/client/src/context/DatabaseBrowserContext.tsx`.

### 2.3 Core Classes and Functions
- FastAPI application and router wiring in `AEGIS/server/app.py`.
- `MapSearchEndpoint`, `MapSearchToolkit`, and `MapRenderingService` orchestrate search processing in `AEGIS/server/routes/search.py`.
- `LocationSearchRequest` request model and validation in `AEGIS/server/schemas/geographics.py`.
- `GIBSService` (NASA WMS client, caching, reprojection) in `AEGIS/server/utils/services/geospatial/gibs.py`.
- `LayerProviderService` for layer alias resolution in `AEGIS/server/utils/services/geospatial/layers.py`.
- `MapService` (Folium rendering) in `AEGIS/server/utils/services/geospatial/maps.py`.
- `NormatimService` geocoding in `AEGIS/server/utils/services/geospatial/normatim.py`.
- `OpenAQService` and `OpenElevationService` data fetchers in `AEGIS/server/utils/services/geospatial/openaq.py` and `AEGIS/server/utils/services/geospatial/elevation.py`.
- `AEGISDatabase`, `SQLiteRepository`, and `PostgresRepository` in `AEGIS/server/database/database.py`, `AEGIS/server/database/sqlite.py`, `AEGIS/server/database/postgres.py`.
- `DataSerializer` for database IO in `AEGIS/server/utils/repository/serializer.py`.
- `searchLocation` HTTP client in `AEGIS/client/src/services/api.ts`.
- `DatabaseBrowserContext` data provider in `AEGIS/client/src/context/DatabaseBrowserContext.tsx`.

---

## 3. Backend API

### 3.1 API Overview
The API is REST-style JSON over HTTP using FastAPI. Routes are grouped under `/maps` and `/browser`. The root path redirects to FastAPI docs. There is no versioning prefix or auth middleware configured in code.

### 3.2 Endpoints

| Method | Route | Description |
|-------|-------|-------------|
| GET | `/` | Redirect to `/docs` |
| POST | `/maps/search` | Perform a geospatial search and render map overlays |
| GET | `/browser/tables` | List available database tables |
| GET | `/browser/tables/{table_name}` | Fetch full table contents |
| GET | `/browser/tables/{table_name}/stats` | Fetch table row/column counts |

### 3.3 Request and Response Models
- `LocationSearchRequest` in `AEGIS/server/schemas/geographics.py` validates inputs such as `datetime`, `address/city/country` or `latitude/longitude`, `filters` (geospatial layers), bbox, map size, and imagery settings.
- The frontend sends `filters` and also maps them to `geospatial_layers` in `AEGIS/client/src/services/api.ts`.
- Responses from `/maps/search` include:
  - `status_message` (string)
  - `payload` (object) containing normalized location fields, optional bbox, and `satellite_imagery` with map HTML, overlay metadata, and image payloads.
- `/browser/tables` responds with `{ tables: [{ name, displayName }] }`.
- `/browser/tables/{table_name}` responds with columns, rows, and counts in a JSON object.

### 3.4 Authentication and Authorization
No authentication or authorization is implemented in the backend. All routes are publicly accessible to any caller who can reach the server.

### 3.5 Error Handling
- Validation errors from Pydantic are returned as HTTP 422 with sanitized `detail` in `AEGIS/server/routes/search.py`.
- Geospatial validation errors return HTTP 400.
- External service failures (NASA GIBS or map rendering) return HTTP 502.
- Browser endpoints return HTTP 404 for unknown tables and HTTP 500 for server errors.
- Unhandled exceptions propagate as FastAPI 500 responses.

---

## 4. Main Components

### 4.1 Component List
- Geospatial UI: `LocationSearch`, `AgenticSearch`, `MapPreview`, `StatsPanel` in `AEGIS/client/src/components/*`.
- Database Browser UI: `DatabaseBrowserPage` and `DatabaseBrowserContext` in `AEGIS/client/src/pages/DatabaseBrowserPage.tsx` and `AEGIS/client/src/context/DatabaseBrowserContext.tsx`.
- Backend search pipeline: `MapSearchEndpoint` plus geospatial services in `AEGIS/server/routes/search.py` and `AEGIS/server/utils/services/geospatial/*`.
- Database browsing API: `AEGIS/server/routes/browser.py` with `DataSerializer`.

### 4.2 Responsibilities and Boundaries
- Frontend owns user input, UI validation, and rendering of results; it does not perform geocoding or data fetching from external providers directly.
- Backend owns geocoding, imagery selection, map rendering, external API calls, and persistence.
- Data persistence is handled by database modules; UI only reads via `/browser/*` endpoints.

---

## 5. Main Application Flows

### 5.1 Typical Request Flow
1. User selects address or coordinates and optional layers in the UI.
2. Frontend builds a `LocationSearchRequest` and POSTs to `/maps/search`.
3. Backend validates the request with `LocationSearchRequest` and normalizes filters.
4. `LocationSanitizationService` and `NormatimService` resolve coordinates and bbox when needed.
5. `MapRenderingService` uses `GIBSService` and `MapService` to build overlays and a Folium map HTML payload.
6. Optional enrichment is fetched from OpenAQ and Open-Elevation.
7. Search session metadata is stored in the database.
8. Frontend renders the map (HTML iframe) and metrics in the stats panel.

### 5.2 Critical Workflows
- User interaction flow: UI inputs -> `/maps/search` -> map preview and stats update in `GeospatialPage`.
- Data ingestion flow: `AEGIS/server/scripts/update_gibs_layers.py` pulls NASA capabilities and stores layer metadata in the database.
- Database browsing flow: UI calls `/browser/tables` and `/browser/tables/{table_name}` to populate the data table.

---

## 6. Data Model and Data Structures

### 6.1 Core Domain Entities
- Location search request: address/city/country or coordinates, optional bbox, map tiles, imagery settings, filters.
- Satellite imagery payload: map HTML, overlay metadata, base64 imagery or WMS URLs.
- Layer metadata: GIBS layer id, projections, tile matrix sets, and meters-per-pixel estimates.
- Search session: request metadata and state (success/failed).

### 6.2 Database Schema
Defined in `AEGIS/server/database/schema.py`:
- `GEONAMES`: geonameid, name, asciiname, alternatenames, latitude, longitude, feature_class, feature_code, country_code, admin codes, population, elevation, timezone, modification_date.
- `GIBS_LAYERS`: layer_id, title, abstract, projections, source_urls, tile_matrix_sets, meters_per_pixel.
- `SEARCH_SESSIONS`: id, created_at, user, country, city, address, coordinates, base_map, geospatial_layers, state.

### 6.3 In-Memory Data Structures
- `CapabilitiesCache` and `ResponseCache` in `AEGIS/server/utils/services/geospatial/gibs.py` for GIBS metadata and imagery caching.
- Layer alias lookup in `LayerProviderService` (`AEGIS/server/utils/services/geospatial/layers.py`).
- Country normalization lookup in `LocationSanitizationService` (`AEGIS/server/utils/services/sanitization.py`).

---

## 7. Component Relationships

### 7.1 Dependency Graph
- Frontend (React) depends on the backend API for search and data browsing.
- Backend depends on geospatial services (Nominatim, GIBS, OpenAQ, Open-Elevation) and database repositories.
- Database layer depends on SQLAlchemy and an embedded SQLite file or external Postgres.

### 7.2 Communication Patterns
- Synchronous HTTP JSON between frontend and backend.
- Backend uses blocking HTTP calls (urllib) executed in `asyncio.to_thread` for external APIs.
- Database access via SQLAlchemy (synchronous).
- No async messaging, queues, or event bus.

---

## 8. WebSocket Implementation

### 8.1 Presence and Purpose
No WebSocket usage was found in the codebase.

### 8.2 Protocol and Message Format
Not applicable.

---

## 9. Database Browsing and Inspection

### 9.1 Admin or Browser Interfaces
The Database Browser UI in `AEGIS/client/src/pages/DatabaseBrowserPage.tsx` surfaces `/browser/*` endpoints for viewing table data and statistics.

### 9.2 Access Control and Security
No access control is implemented; all database browser endpoints are available without authentication.

---

## 10. Training Pipeline and Dashboard

### 10.1 Training Workflow
No training pipeline is implemented in this repository.

### 10.2 Model Artifacts
No model artifact storage or versioning is defined.

### 10.3 Dashboard and Monitoring
There is a UI stats panel for map results, but no training or model monitoring dashboards.

---

## 11. Known Limitations and Open Questions
- Agentic search fields and `MAPS_AGENTIC_ROUTE` are present, but no backend route or LLM pipeline is implemented.
- `configurations.json` uses `llm_runtime_defaults`, while code expects `llm_defaults`, so LLM defaults may not load from the config file.
- Database paging fields in `configurations.json` (`select_page_size`, `browser_page_size`) are not used in backend code.
- `MapLayerUpdateRequest` exists in schemas but has no corresponding route.
- No authentication, rate limiting, or request quotas for external services.
- GEONAMES table exists but no ingestion workflow is defined in the repo.
