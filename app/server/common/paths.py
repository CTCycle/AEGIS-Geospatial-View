from __future__ import annotations

import os
import tempfile
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
ENV_EXAMPLE_FILE_PATH = SETTING_PATH / ".env.example"
DATABASE_FILENAME = "database.db"
CLIENT_DIST_PATH = APP_DIR / "client" / "dist" / "browser"
CLIENT_ASSETS_PATH = CLIENT_DIST_PATH / "assets"
CLIENT_INDEX_FILE_PATH = CLIENT_DIST_PATH / "index.html"
CONFIGURATIONS_FILE = SETTING_PATH / "configurations.json"

###############################################################################
def resolve_runtime_data_root() -> Path:
    override = os.getenv("AEGIS_RUNTIME_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        temp_dir = tempfile.gettempdir().strip()
        if temp_dir:
            return Path(temp_dir) / "AEGIS Geospatial View"

    return ROOT_DIR / ".runtime"

###############################################################################
def resolve_database_file_path() -> Path:
    return resolve_runtime_data_root() / DATABASE_FILENAME


RUNTIME_DATA_PATH = resolve_runtime_data_root()
DATABASE_FILE_PATH = resolve_database_file_path()

ROOT_ROUTE = "/"
DOCS_ROUTE = "/docs"
FASTAPI_ROOT_ENDPOINT = ROOT_ROUTE
FASTAPI_DOCS_ENDPOINT = DOCS_ROUTE
FASTAPI_API_PREFIX = "/api"
FASTAPI_ASSETS_ENDPOINT = "/assets"
FASTAPI_SPA_FALLBACK_ENDPOINT = "/{full_path:path}"
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
CONVERSATIONS_ROUTER_PREFIX = "/conversations"
CONVERSATIONS_ROOT_ROUTE = ""
CONVERSATION_RUNS_ROUTE = "/{conversation_id}/runs"

CONVERSATION_REALTIME_ROUTE = "/{conversation_id}/realtime"

CONVERSATION_RUN_EVENTS_ROUTE = "/{conversation_id}/runs/{run_id}/events"
CONVERSATION_RUN_STEERING_ROUTE = "/{conversation_id}/runs/{run_id}/steering"
CONVERSATION_RUN_CANCEL_ROUTE = "/{conversation_id}/runs/{run_id}/cancel"
