# AEGIS Geospatial View

## 1. Project Overview
AEGIS Geospatial View turns natural-language location prompts or raw coordinates into normalized bounding boxes and previewable map tiles. The stack pairs a FastAPI backend (geocoding, NASA GIBS layer selection, Folium rendering, and metadata caching) with a Vite + React frontend for interactive searches. It relies on OpenStreetMap Nominatim and optional LLM-powered routing (local Ollama by default) to keep responses consistent and fast.

## 2. Installation

### 2.1 Windows (One-Click Setup - No Prerequisites Required)
Launch `AEGIS/start_on_windows.bat` to provision everything automatically:

1. Download and install **portable Python 3.12** locally (no global install)
2. Install **uv** locally (portable Python package manager)
3. Download and install **portable Node.js v22** locally (no global install)
4. Install all Python and Node.js dependencies
5. Build the React frontend
6. Launch the FastAPI backend and Vite frontend preview
7. Open your browser to the application interface

**First Run**: Expect a 2-5 minute setup while Python, Node.js, and dependencies download to `AEGIS/resources/runtimes/`.  
**Subsequent Runs**: Launches in seconds using the cached runtimes and installed packages.

> **Note**: Everything stays inside the project folder. Move the folder and the portable runtimes move with it.

### 2.2 macOS / Linux / Manual Setup
**Prerequisites:**
- **Python 3.12**
- **Node.js 18+** and npm
- A recent version of `pip` (or `uv`)

**Setup Steps:**
1. Create and activate a Python 3.12 environment.
2. Install backend dependencies from the repository root with `pip install -e . --use-pep517` (or `uv pip install -e .`).
3. (Optional) Install extras for tooling with `pip install -e .[dev]`.
4. Navigate to `AEGIS/client` and run `npm install` to install frontend dependencies.

## 3. How to use

### 3.1 Windows
Run `AEGIS/start_on_windows.bat` to start both servers together:

- First run: downloads runtimes and dependencies (2-5 minutes)
- Later runs: reuses cached installations (few seconds)

The launcher opens the interface at `http://127.0.0.1:7861`, proxied to the FastAPI backend at `http://127.0.0.1:8000`.

### 3.2 macOS / Linux / Manual
Start backend and frontend from separate terminals:

```bash
# Terminal 1: start backend
uvicorn AEGIS.server.app:app --host 0.0.0.0 --port 8000

# Terminal 2: start frontend (Vite)
cd AEGIS/client
npm run dev -- --host 127.0.0.1 --port 5173
```

The React UI runs on the printed Vite URL (default `http://127.0.0.1:5173`), and the API docs are available at `http://127.0.0.1:8000/docs`. To preview a production build locally, run `npm run build && npm run preview`.

### 3.3 Using the Application
Enter a place name or coordinates, choose imagery options, and request a preview. The backend normalizes the query, selects a NASA GIBS layer when applicable, and returns bbox metadata, meters-per-pixel estimates, and Folium-rendered map imagery for the UI to display.

- **API**: `POST /maps/search` accepts free text or coordinates plus optional filters (layer ids), bbox overrides, datetime, and map dimensions. Responses include normalized coordinates, bbox in EPSG:4326, chosen layer, and imagery payloads suitable for direct rendering.
- **UI**: The search panel accepts addresses or latitude/longitude pairs, lets you tweak layer and dimension inputs, and shows updated map previews returned by the backend.
- **LLM routing (optional)**: If enabled via configuration, the backend uses local Ollama by default (cloud providers are configurable in `AEGIS/settings/server_configurations.json`) to interpret intent or choose layers.

## 4. Setup and Maintenance
Run `AEGIS/setup_and_maintenance.bat` for routine tasks:

- **Remove logs** - clear accumulated files in `AEGIS/resources/logs`
- **Uninstall app** - delete cached runtimes, locks, and virtual environments created by the launchers

## 5. Resources
Project assets and outputs live under `AEGIS`:

- **server/** FastAPI app, routers, schemas, services, and configuration loaders for geocoding, layer selection, and map rendering.
- **client/** React + Vite frontend for submitting searches and viewing map previews.
- **resources/database/** Cached geospatial datasets used by search and normalization routines.
- **resources/logs/** Rolling backend and launcher logs; safe to clear through the maintenance script.
- **resources/templates/** Starter assets such as the `.env` template and ancillary files referenced during setup.
- **resources/runtimes/** Portable Python, uv, and Node.js installations managed by the Windows launcher.

## 6. Configuration
Runtime options are defined through environment files and frontend build variables.

| Variable | Description |
|----------|-------------|
| FASTAPI_HOST | Host address for the FastAPI server (`AEGIS/settings/.env`, default 127.0.0.1) |
| FASTAPI_PORT | Port for the FastAPI server (`AEGIS/settings/.env`, default 8002 for manual runs; launcher defaults to 8000) |
| MPLBACKEND | Matplotlib backend used for server-side rendering (`AEGIS/settings/.env`, default Agg) |
| VITE_API_BASE_URL | Base URL for API calls from the React app (`AEGIS/client/.env`, default falls back to Vite dev proxy) |


Copy `AEGIS/resources/templates/.env` into `AEGIS/settings/.env` (backend) and create `AEGIS/client/.env` for frontend overrides when needed.

## 7. License
This project is licensed under the terms of the MIT license. See `LICENSE` for details.
