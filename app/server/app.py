from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from server.api.chat import router as chat_router
from server.api.geospatial import router as geospatial_router
from server.api.search import router as search_router
from server.common.constants import (
    CLIENT_ASSETS_PATH,
    CLIENT_DIST_PATH,
    CLIENT_INDEX_FILE_PATH,
    FASTAPI_API_PREFIX,
    FASTAPI_ASSETS_ENDPOINT,
    FASTAPI_DOCS_ENDPOINT,
    FASTAPI_ROOT_ENDPOINT,
    FASTAPI_SPA_FALLBACK_ENDPOINT,
)
from server.configurations import get_server_settings
from server.repositories.database import get_database
from server.repositories.database.initializer import initialize_database, seed_reference_catalog
from server.services.chat.composition import build_chat_runtime
from server.services.search.composition import build_search_runtime
from server.services.startup_validation import run_startup_validations

###############################################################################
def _client_build_available() -> bool:
    return Path(CLIENT_INDEX_FILE_PATH).is_file()

###############################################################################
def _resolve_client_file(full_path: str) -> Path | None:
    client_root = Path(CLIENT_DIST_PATH).resolve()
    requested_path = (client_root / full_path).resolve()

    if not requested_path.is_relative_to(client_root):
        return None

    if requested_path.is_file():
        return requested_path

    return None

###############################################################################
def serve_client_root() -> FileResponse:
    return FileResponse(CLIENT_INDEX_FILE_PATH)

###############################################################################
def serve_client_path(full_path: str) -> FileResponse:
    client_file = _resolve_client_file(full_path)
    if client_file is not None:
        return FileResponse(client_file)
    return FileResponse(CLIENT_INDEX_FILE_PATH)

###############################################################################
def redirect_root_to_docs() -> RedirectResponse:
    return RedirectResponse(FASTAPI_DOCS_ENDPOINT)


@asynccontextmanager
async def app_lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = get_server_settings()
    database = get_database()

    initialize_database(database.backend)
    seed_reference_catalog(database.backend)

    search_runtime = build_search_runtime()
    chat_runtime = build_chat_runtime(search_runtime.search_orchestrator)

    application.state.search_runtime = search_runtime
    application.state.chat_runtime = chat_runtime

    chat_runtime.settings_service.get_settings()

    run_startup_validations(settings)

    if settings.vectors.auto_sync_on_start:
        chat_runtime.vector_indexer.sync()

    yield


def create_app() -> FastAPI:
    application = FastAPI(title="AEGIS API", lifespan=app_lifespan)

    application.include_router(search_router, prefix=FASTAPI_API_PREFIX)
    application.include_router(chat_router, prefix=FASTAPI_API_PREFIX)
    application.include_router(geospatial_router, prefix=FASTAPI_API_PREFIX)

    if _client_build_available():
        if Path(CLIENT_ASSETS_PATH).is_dir():
            application.mount(
                FASTAPI_ASSETS_ENDPOINT,
                StaticFiles(directory=CLIENT_ASSETS_PATH),
                name="assets",
            )
        application.add_api_route(
            FASTAPI_ROOT_ENDPOINT,
            serve_client_root,
            methods=["GET"],
            include_in_schema=False,
        )
        application.add_api_route(
            FASTAPI_SPA_FALLBACK_ENDPOINT,
            serve_client_path,
            methods=["GET"],
            include_in_schema=False,
        )

    else:
        application.add_api_route(
            FASTAPI_ROOT_ENDPOINT,
            redirect_root_to_docs,
            methods=["GET"],
            include_in_schema=False,
        )

    return application


app = create_app()
