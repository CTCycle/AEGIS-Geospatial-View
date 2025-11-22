# AEGIS Geospatial View

## Overview
AEGIS Geospatial View is a FastAPI + NiceGUI application that geocodes free-text locations, sanitizes coordinates, and previews NASA GIBS satellite imagery. It combines OpenStreetMap Nominatim for search, a cached catalog of GIBS layers, and optional LLM-powered “agentic” routing (local Ollama by default, or OpenAI/Gemini if enabled) to turn natural language prompts into precise map requests.

## Features
- `/maps/search` endpoint resolves place names, bounding boxes, and dates into harmonized coordinates and returns a WMS image plus metadata (e.g., meters_per_pixel, normalized bbox).
- `/maps/agentic` endpoint lets an LLM interpret natural language prompts, pick a geospatial layer, and call the same imagery pipeline.
- NiceGUI front end with form controls for coordinates, bbox, date/time, and layer selection, plus a live image preview sourced from the backend response.
- Built-in SQLite database initialization for cached geospatial data and GIBS layer definitions; logging under `AEGIS/resources/logs`.
- Configurable imagery size, bbox precision, and network timeouts through `AEGIS/setup/configurations.json`.

## Quick start (Windows)
1. Update `AEGIS/setup/.env` if you need to change host/port (`FASTAPI_HOST`, `FASTAPI_PORT`) or matplotlib backend.
2. From the repository root, run `AEGIS\start_on_windows.bat`. The script downloads an embeddable Python 3.12, syncs dependencies with `uv`, and launches `uvicorn` with the NiceGUI UI mounted at `/ui` (default http://127.0.0.1:800/ui).
3. If your antivirus blocks the embeddable Python download or execution, add an exception for the downloaded `AEGIS\setup\python` directory.

## Manual run (any OS)
1. Ensure Python 3.12 is available.
2. Install dependencies from the repository root: `pip install .` (or `uv pip install .`).
3. Start the app: `uvicorn AEGIS.src.app:app --host 0.0.0.0 --port 8000`.
4. Open the UI at `http://localhost:8000/ui`.

## Configuration
- Core settings: `AEGIS/setup/configurations.json` (API base URL, UI mount/port, Nominatim and GIBS parameters).
- Environment variables: `AEGIS/setup/.env` (host/port, plotting backend) with an optional template in `AEGIS/resources/templates/.env` for LangSmith and plotting defaults.
- Model routing defaults and available cloud providers are defined in `AEGIS/src/packages/constants.py`.

## Notes on imagery resolution
- GIBS layers such as VIIRS Corrected Reflectance have native resolutions in the 375–500 m range; higher WIDTH/HEIGHT values on tiny bounding boxes will only interpolate pixels.
- Responses include a normalized bbox and `meters_per_pixel` so clients can assess the effective ground resolution for each request.

## License
This project is licensed under the terms of the MIT license. See the LICENSE file for details.

