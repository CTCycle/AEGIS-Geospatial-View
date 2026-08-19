# System Overview

Last updated: 2026-08-02

## Scope

This branch describes the implemented system across `app/` and `settings/`.

## Application Shape

AEGIS Geospatial View is a two-tier application:

- Frontend: Angular 22 standalone SPA in `app/client/src`
- Backend: FastAPI application in `app/server`

The backend exposes `/api` routes for chat orchestration, geospatial capability access, and map search. The frontend consumes those routes and renders the chat-and-map workspace. The primary UI path uses a versioned WebSocket at `/api/conversations/{conversation_id}/realtime`; durable run events are replayed by sequence after reconnect. Direct chat-turn, NDJSON stream, and in-process job routes remain available for API clients and bounded test flows, but are not used by the interactive UI.

## Entry Points

- Backend import/runtime entry: `app/server/app.py`
- Backend ASGI app object: `create_app()`
- Frontend bootstrap: `app/client/src/main.ts`
- Frontend root component: `app/client/src/app/app.component.ts`
- Frontend routes: `app/client/src/app/app.routes.ts`
- Windows launcher: `start_on_windows.ps1`

## Backend Startup Behavior

`app_lifespan` composes the server runtime and:

- loads settings
- ensures relational schema
- seeds auto-generated credential encryption key material
- seeds reference catalog data
- composes search and chat runtimes
- seeds chat settings through the settings service
- runs startup validation

The composition root also wires the durable conversation/run lifecycle, steering,
event replay, and the in-process background-job worker. A runtime dependency is
not constructed ad hoc inside a request handler.

`create_app()` mounts API routers under `/api`, serves the built SPA when `app/client/dist/browser/index.html` exists, and otherwise redirects `/` to `/docs`.

## External Integrations

Implemented service integrations include:

- OpenStreetMap and Nominatim
- Overpass
- Overture Maps, OpenAddresses, OurAirports, Natural Earth, and local open-data snapshots
- NASA GIBS
- NASA FIRMS, NOAA, USGS, FEMA, Census, Eurostat, EEA, and ESA
- OpenAQ
- Open-Meteo
- PVGIS
- RainViewer
- TomTom
- OpenChargeMap
- OpenFreeMap and other public basemap styles
- GTFS, GTFS-Realtime, and Mobility Database feed catalogs
- Windy Webcams and configured local camera networks
- Ollama
- OpenAI-compatible providers
- Google-compatible providers
- DeepSeek and OpenCode Zen/OpenCode Go
