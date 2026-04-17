from __future__ import annotations

import os
import warnings

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from AEGIS.server.api.access_keys import router as access_keys_router
from AEGIS.server.api.chat import router as chat_router
from AEGIS.server.api.search import router as search_router
from AEGIS.server.configurations import get_server_settings
from AEGIS.server.repositories.database.initializer import initialize_sqlite_database
from AEGIS.server.services.vector.indexer import VectorIndexer
from AEGIS.server.utils.constants import (
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


###############################################################################
app = FastAPI(
    title=FASTAPI_TITLE,
    version=FASTAPI_VERSION,
    description=FASTAPI_DESCRIPTION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=build_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def initialize_embedded_database_on_first_startup() -> None:
    settings = get_server_settings().database
    if not settings.embedded_database:
        return
    initialize_sqlite_database(settings)


@app.on_event("startup")
def bootstrap_vector_index_on_first_startup() -> None:
    if not get_server_settings().vectors.auto_sync_on_start:
        return
    VectorIndexer().bootstrap_if_missing()

routers = [search_router, chat_router, access_keys_router]

for router in routers:
    app.include_router(router, prefix="/api")


if packaged_client_available():
    client_dist_path = get_client_dist_path()
    assets_path = os.path.join(client_dist_path, "assets")

    if os.path.isdir(assets_path):
        app.mount("/assets", StaticFiles(directory=assets_path), name="spa-assets")

    @app.get("/", include_in_schema=False)
    def serve_spa_root() -> FileResponse:
        return FileResponse(os.path.join(client_dist_path, "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa_entrypoint(full_path: str) -> FileResponse:
        requested_path = os.path.join(client_dist_path, full_path)
        if os.path.isfile(requested_path):
            return FileResponse(requested_path)
        return FileResponse(os.path.join(client_dist_path, "index.html"))

else:

    @app.get("/")
    def redirect_to_docs() -> RedirectResponse:
        return RedirectResponse(url="/docs")
