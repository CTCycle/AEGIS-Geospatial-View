# AEGIS Geospatial View

# 1. Introduction
AEGIS Geospatial View delivers a FastAPI backend and a React (Vite) frontend for converting natural-language place descriptions or raw coordinates into normalized bounding boxes and previewable map imagery. It blends OpenStreetMap Nominatim search, NASA GIBS layers, Folium map rendering, and optional LLM-powered “agentic” routing to help users rapidly request geospatial tiles with consistent metadata.

## Core capabilities
- Geocode free-text locations into harmonized coordinates and bounding boxes via `/maps/search`, returning imagery plus normalized metadata (e.g., bbox, meters-per-pixel).
- Render WMS imagery and interactive map previews using Folium with configurable tiles, overlays, and image dimensions.
- Cache NASA GIBS layer definitions and meters-per-pixel metadata for quicker lookups and deterministic layer selection.
- Optional LLM-backed prompt routing (Ollama locally by default, OpenAI/Gemini if enabled) to interpret intent and select layers or parameters.
- React UI for address/coordinate input, layer selection, and live map previews sourced from the backend response.
- Out-of-the-box logging and local resource folders for data, templates, and cached artifacts.

# 2. Installation
- **Supported platforms**: Windows scripted setup; manual installation on macOS/Linux/Windows with Python 3.12+ and Node 18+.
- **Prerequisites**: Python 3.12, `pip` (or `uv`), Node.js 18+, npm, network access to Nominatim and NASA GIBS endpoints. Update `AEGIS/setup/settings/.env` for host/port overrides before startup.

Standard setup:
1. Clone the repository and open a terminal at the repo root.
2. Install Python dependencies: `pip install .` (or `uv pip install .`).
3. Install frontend deps: `cd AEGIS/client && npm install`.

## Optional: Additional installation modes
- **Windows one-step bootstrap**: run `AEGIS\\start_on_windows.bat` to download an embeddable Python 3.12, sync dependencies with `uv`, and launch the FastAPI server (defaults to `http://127.0.0.1:8000`).
- **Editable/development install**: run `AEGIS\\setup_and_maintenance.bat` → “Enable root path imports” to install the backend in editable mode using the bundled `uv`.
- **Scripted maintenance**: the same menu exposes log cleanup and uninstall helpers; see Maintenance below.

# 4. Usage
Backend (any OS):
1. Ensure environment variables in `AEGIS/setup/settings/.env` reflect the desired host/port.
2. From the repo root: `uvicorn AEGIS.server.app:app --host 0.0.0.0 --port 8000`.

Frontend:
1. `cd AEGIS/client`
2. Dev server: `npm run dev -- --host --port 5173` then open the printed URL.  
   Production preview: `npm run build && npm run preview`.

## Subsections for main workflows
- **Map search via API**  
  - Endpoint: `POST /maps/search`  
  - Typical payload: coordinates or free text plus optional `filters` (layer ids), `bbox`, `datetime`, and map dimensions.  
  - Response: normalized coordinates, chosen layer, bbox in EPSG:4326, meters-per-pixel estimate, and WMS/Folium imagery encoded for display. Validation errors are normalized with clear context.

- **Layer and imagery handling**  
  - Layers are normalized by `MapSearchToolkit` and `LayerProviderService`, defaulting to the configured GIBS layer if none is supplied.  
  - Bboxes are validated/clamped, and Folium renders maps with configurable base tiles and overlay layers.  
  - GIBS metadata is cached with configurable TTL and WMS/WMTS endpoints for EPSG:4326/3857/3413/3031.

- **Agentic routing (optional)**  
  - Defaults to local Ollama (`llama3.1:8b`), with cloud fallbacks configured in `server_configurations.json`.  
  - Runtime toggles (provider, model, cloud enablement, temperature) are tracked via `LLMRuntimeConfig` and reflected in responses for clients to react to revisions.

### Maintenance or operational tools
- `AEGIS/start_on_windows.bat`: bootstrap Python, install backend deps with `uv`, and start the API.
- `AEGIS/setup_and_maintenance.bat`: menu for enabling editable installs, updating the project, clearing `AEGIS/resources/logs`, or uninstalling cached tooling.
- `AEGIS/server/scripts/update_geonames.py` and `AEGIS/server/scripts/update_gibs_layers.py`: helper scripts for refreshing cached geospatial databases and GIBS layer catalogs.

### Resources
- `AEGIS/server`: FastAPI app, routers, schemas, services, and configuration loaders.
- `AEGIS/client`: React/Vite frontend.
- `AEGIS/setup`: Embeddable Python, `uv` tooling, settings, and automation scripts.
- `AEGIS/resources/database`: cached geospatial data; `AEGIS/resources/logs`: runtime logs; `AEGIS/resources/templates`: env templates and supporting assets.
- `LICENSE`, `pyproject.toml`, `uv.lock`: project metadata and dependency lock.

# 5. License
This project is licensed under the MIT License. See `LICENSE` for details.

