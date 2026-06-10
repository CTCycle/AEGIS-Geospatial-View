from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
APP_DIR = ROOT_DIR / "app"
PROJECT_DIR = APP_DIR
SETTING_PATH = ROOT_DIR / "settings"
RESOURCES_PATH = APP_DIR / "resources"
MODELS_PATH = RESOURCES_PATH / "models"
SOURCES_PATH = RESOURCES_PATH / "sources"
LOGS_PATH = RESOURCES_PATH / "logs"
ENV_FILE_PATH = SETTING_PATH / ".env"
DATABASE_FILENAME = "database.db"
DATABASE_FILE_PATH = RESOURCES_PATH / DATABASE_FILENAME
CLIENT_DIST_PATH = APP_DIR / "client" / "dist" / "browser"
CLIENT_ASSETS_PATH = CLIENT_DIST_PATH / "assets"
CLIENT_INDEX_FILE_PATH = CLIENT_DIST_PATH / "index.html"
CONFIGURATIONS_FILE = SETTING_PATH / "configurations.json"

ROOT_ROUTE = "/"
DOCS_ROUTE = "/docs"
FASTAPI_ROOT_ENDPOINT = ROOT_ROUTE
FASTAPI_DOCS_ENDPOINT = DOCS_ROUTE
FASTAPI_API_PREFIX = "/api"
FASTAPI_ASSETS_ENDPOINT = "/assets"
FASTAPI_SPA_FALLBACK_ENDPOINT = "/{full_path:path}"
MAPS_ROUTER_PREFIX = "/maps"
MAPS_SEARCH_ROUTE = "/search"
MAPS_CATALOG_ROUTE = "/catalog"
MAPS_OSM_BASEMAP_TILE_ROUTE = "/basemaps/osm/{z}/{x}/{y}.png"
MAPS_JOBS_ROUTE = "/jobs"
MAPS_JOB_ROUTE = "/jobs/{job_id}"
JOBS_ROUTER_PREFIX = "/jobs"
JOBS_JOB_ROUTE = "/{job_id}"
JOBS_JOB_EVENTS_ROUTE = "/{job_id}/events"
JOBS_JOB_CANCEL_ROUTE = "/{job_id}/cancel"
CHAT_ROUTER_PREFIX = "/chat"
CHAT_TURN_ROUTE = "/turn"
CHAT_STREAM_ROUTE = "/stream"
CHAT_JOBS_ROUTE = "/jobs"
CHAT_MODELS_ROUTE = "/models"
CHAT_SETTINGS_ROUTE = "/settings"
CHAT_OLLAMA_REFRESH_ROUTE = "/models/ollama/refresh"
CHAT_OLLAMA_PULL_ROUTE = "/models/ollama/pull"
CHAT_OLLAMA_HEALTH_ROUTE = "/models/ollama/health"
