from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from nicegui import ui

from AEGIS.src.app.backend.endpoints.search import router as search_router
from AEGIS.src.app.frontend.interface import create_interface
from AEGIS.src.packages.configurations import FASTAPI_SETTINGS, UI_RUNTIME_SETTINGS
from AEGIS.src.packages.logger import logger
from AEGIS.src.packages.utils.repository.database import database

###############################################################################
# initialize the database if it has not been created
if not os.path.exists(database.db_path):
    logger.info("Database not found, creating instance and making all tables")
    database.initialize_database()
    logger.info("AEGIS database has been initialized successfully.")

app = FastAPI(
    title=FASTAPI_SETTINGS.title,
    version=FASTAPI_SETTINGS.version,
    description=FASTAPI_SETTINGS.description,
)

app.include_router(search_router)

###############################################################################
create_interface()
ui.run_with(
    app,
    mount_path=UI_RUNTIME_SETTINGS.mount_path,
    title=UI_RUNTIME_SETTINGS.title,
    show_welcome_message=UI_RUNTIME_SETTINGS.show_welcome_message,
    reconnect_timeout=UI_RUNTIME_SETTINGS.reconnect_timeout,
)

@app.get("/")
def redirect_to_ui() -> RedirectResponse:
    return RedirectResponse(url=UI_RUNTIME_SETTINGS.redirect_path)
