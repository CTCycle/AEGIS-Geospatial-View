# AEGIS Geospatial View Architecture

Last updated: 2026-03-28  
Scope: `AEGIS/` and `tests/`

## 1. System Overview

AEGIS Geospatial View accepts address or coordinate-based location searches, resolves location data, composes map overlays (NASA GIBS and OpenAQ), enriches results with elevation data, and returns a rendered map payload for the React UI.

Main stack:
- Frontend: React 18 + TypeScript 5 + Vite 6 (`AEGIS/client`)
- Backend: FastAPI (`AEGIS/server`)
- Persistence: SQLAlchemy with SQLite (embedded) or PostgreSQL (external)
- Mapping/rendering: Folium + Pillow

## 2. Runtime and Deployment Assumptions

- Python requirement: `>=3.14` (`pyproject.toml`)
- Frontend runtime: Node.js 22 (portable runtime installed by launcher)
- Local launcher: `AEGIS/start_on_windows.bat`
- Test runner: `tests/run_tests.bat`
- Default runtime configuration source: `AEGIS/settings/.env`

Important ports:
- `.env` examples default to backend `5002`, frontend `5000`
- launcher fallback defaults are also `5002`/`5000`
- test runner fallback defaults are `8000`/`7861`, but `.env` overrides are applied when present

## 3. Repository Layout

- `AEGIS/client`: React application
- `AEGIS/server`: FastAPI application
- `AEGIS/server/api`: route handlers
- `AEGIS/server/domain`: request/response models
- `AEGIS/server/services`: geospatial and job services
- `AEGIS/server/repositories`: DB backends, schemas, serializers
- `AEGIS/server/configurations`: server settings loader
- `AEGIS/server/utils`: constants, logger, helpers
- `AEGIS/settings`: `.env` and JSON configuration
- `AEGIS/resources`: DB file, logs, templates, other local resources
- `tests/e2e`: Playwright+pytest end-to-end tests
- `runtimes`: portable Python/uv/Node and runtime lockfile

## 4. Backend API Surface

Primary router prefix: `/maps`.

Routes:
- `POST /maps/search`: synchronous location search and map payload generation
- `POST /maps/jobs`: start async map search job
- `GET /maps/jobs/{job_id}`: poll job status
- `DELETE /maps/jobs/{job_id}`: request cooperative cancellation

Compatibility mount:
- The same routes are also exposed under `/api` (for frontend proxy paths), for example `/api/maps/search`.

Root behavior:
- If packaged SPA is available in Tauri mode, `/` serves frontend assets.
- Otherwise `/` redirects to `/docs`.

## 5. Core Backend Flow

1. Request enters `MapSearchEndpoint` in `AEGIS/server/api/search.py`.
2. Payload is validated via `LocationSearchRequest`.
3. Location normalization/geocoding is performed by sanitization + Nominatim services.
4. Overlay selection and map composition are performed by `MapRenderingService`.
5. Optional enrichment is fetched from Open-Elevation and OpenAQ service integrations.
6. Search session metadata is persisted through `DataSerializer`.
7. JSON response returns `status_message` and `payload` with `satellite_imagery` content.

## 6. Background Job Model

- Job execution is thread-based via `AEGIS/server/services/jobs.py`.
- `JobManager` tracks status, progress, result, and error per job.
- Cancellation is cooperative (`stop_requested`) and must be checked by worker logic.
- Job routes live in the same `MapSearchEndpoint` as synchronous search.

See `assets/docs/BACKGROUND_JOBS.md` for full details.

## 7. Data Model Snapshot

Main SQLAlchemy entities in `AEGIS/server/repositories/schemas/models.py`:
- `GEONAMES`
- `GIBS_LAYERS`
- `SEARCH_SESSIONS`

Database backend choice:
- Embedded SQLite when `DB_EMBEDDED=true`
- PostgreSQL when `DB_EMBEDDED=false`

## 8. Frontend Architecture

- Single-page shell in `AEGIS/client/src/App.tsx`.
- Primary workspace page: `AEGIS/client/src/pages/GeospatialPage.tsx`.
- Layout: left search toolbar + right map canvas.
- Service layer for API calls: `AEGIS/client/src/services/api.ts`.

## 9. External Integrations

- OpenStreetMap Nominatim
- NASA GIBS
- OpenAQ
- Open-Elevation

These integrations are network-dependent; failures are surfaced as request errors (typically 400/502 depending on failure type).

## 10. Known Constraints

- No built-in authentication/authorization middleware for map endpoints.
- External API availability can affect E2E and manual runs.
- Job execution is in-process and thread-based, not queue-worker distributed.
