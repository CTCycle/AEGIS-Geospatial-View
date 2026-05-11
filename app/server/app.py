from __future__ import annotations

import os
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from server.api.chat import router as chat_router
from server.api.geospatial import router as geospatial_router
from server.api.search import router as search_router
from server.configurations import get_server_settings
from server.repositories.database.initializer import initialize_sqlite_database
from server.services.chat.composition import build_chat_runtime
from server.services.search.composition import build_search_runtime
from server.services.startup_validation import run_startup_validations
from server.services.vector.indexer import VectorIndexer
from server.common.constants import (
    FASTAPI_DESCRIPTION,
    FASTAPI_TITLE,
    FASTAPI_VERSION,
)

warnings.filterwarnings("ignore", category=FutureWarning)


def build_cors_origins() -> list[str]:
    ui_host = os.getenv("UI_HOST", "127.0.0.1").strip() or "127.0.0.1"
    ui_port = os.getenv("UI_PORT", "4980").strip() or "4980"
    host_variants = {ui_host}
    if ui_host == "127.0.0.1":
        host_variants.add("localhost")
    elif ui_host == "localhost":
        host_variants.add("127.0.0.1")
    origins: list[str] = []
    for host in host_variants:
        origins.append(f"http://{host}:{ui_port}")
        origins.append(f"https://{host}:{ui_port}")
    return origins


def tauri_mode_enabled() -> bool:
    value = os.getenv("AEGIS_TAURI_MODE", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def get_client_dist_path() -> str:
    project_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(project_path, "client", "dist")


def packaged_client_available() -> bool:
    return tauri_mode_enabled() and os.path.isdir(get_client_dist_path())


def serve_spa_root() -> FileResponse:
    return FileResponse(os.path.join(get_client_dist_path(), "index.html"))


def serve_spa_entrypoint(full_path: str) -> FileResponse:
    client_dist_path = get_client_dist_path()
    requested_path = os.path.join(client_dist_path, full_path)
    if os.path.isfile(requested_path):
        return FileResponse(requested_path)
    return FileResponse(os.path.join(client_dist_path, "index.html"))


def redirect_to_docs() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    settings = get_server_settings().database
    if settings.embedded_database:
        initialize_sqlite_database(settings)

    search_runtime = build_search_runtime()
    chat_runtime = build_chat_runtime(search_runtime.search_orchestrator)
    app.state.search_runtime = search_runtime
    app.state.chat_runtime = chat_runtime
    run_startup_validations()

    if get_server_settings().vectors.auto_sync_on_start:
        VectorIndexer().bootstrap_if_missing()

    yield


###############################################################################
def create_app() -> FastAPI:
    app = FastAPI(
        title=FASTAPI_TITLE,
        version=FASTAPI_VERSION,
        description=FASTAPI_DESCRIPTION,
        lifespan=app_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=build_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(search_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(geospatial_router, prefix="/api")

    if packaged_client_available():
        client_dist_path = get_client_dist_path()
        assets_path = os.path.join(client_dist_path, "assets")

        if os.path.isdir(assets_path):
            app.mount("/assets", StaticFiles(directory=assets_path), name="spa-assets")
        app.add_api_route("/", serve_spa_root, methods=["GET"], include_in_schema=False)
        app.add_api_route(
            "/{full_path:path}",
            serve_spa_entrypoint,
            methods=["GET"],
            include_in_schema=False,
        )
    else:
        app.add_api_route("/", redirect_to_docs, methods=["GET"])

    return app


app = create_app()
