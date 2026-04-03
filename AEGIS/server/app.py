from __future__ import annotations

import os
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from AEGIS.server.api.chat import router as chat_router
from AEGIS.server.api.search import router as search_router
from AEGIS.server.utils.constants import (
    FASTAPI_DESCRIPTION,
    FASTAPI_TITLE,
    FASTAPI_VERSION,
)
from AEGIS.server.utils.variables import env_variables  # noqa: F401


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

routers = [search_router, chat_router]

for router in routers:
    app.include_router(router)
    app.include_router(router, prefix="/api", include_in_schema=False)


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
