# System Overview

Last updated: 2026-06-02

## Scope

This branch describes the implemented system across `app/`, `settings/`, and `release/`.

## Application Shape

AEGIS Geospatial View is a two-tier application:

- Frontend: Angular 19 standalone SPA in `app/client/src`
- Backend: FastAPI application in `app/server`

The backend exposes `/api` routes for chat orchestration, geospatial capability access, and map search. The frontend consumes those routes and renders the chat-and-map workspace.

## Entry Points

- Backend import/runtime entry: `app/server/app.py`
- Backend ASGI app object: `create_app()`
- Frontend bootstrap: `app/client/src/main.ts`
- Frontend root component: `app/client/src/app/app.component.ts`
- Frontend routes: `app/client/src/app/app.routes.ts`
- Desktop packaging config: `app/client/src-tauri/tauri.conf.json`
- Windows packaging script: `release/tauri/build_with_tauri.bat`

## Backend Startup Behavior

`app_lifespan` composes the server runtime and:

- loads settings
- ensures relational schema
- composes search and chat runtimes
- seeds chat settings through the settings service
- runs startup validation
- optionally syncs vectors

`create_app()` mounts API routers under `/api`, serves the packaged SPA when `app/client/dist/browser/index.html` exists, and otherwise redirects `/` to `/docs`.

## External Integrations

Implemented service integrations include:

- OpenStreetMap and Nominatim
- Overpass
- NASA GIBS
- OpenAQ
- Open-Meteo
- PVGIS
- RainViewer
- TomTom
- Geoapify
- Ollama
- OpenAI-compatible providers
- Google-compatible providers
