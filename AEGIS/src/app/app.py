from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from nicegui import ui

from AEGIS.src.app.backend.endpoints.search import router as search_router
from AEGIS.src.app.frontend.interface import create_interface
from AEGIS.src.packages.configurations import APP_CONFIGURATIONS
from AEGIS.src.packages.logger import logger
from AEGIS.src.packages.utils.repository.database import database

APP_CONFIG = APP_CONFIGURATIONS

###############################################################################
# initialize the database if it has not been created
if not os.path.exists(database.db_path):
    logger.info("Database not found, creating instance and making all tables")
    database.initialize_database()
    logger.info("AEGIS database has been initialized successfully.")

app = FastAPI(
    title=APP_CONFIG.backend.title,
    version=APP_CONFIG.backend.version,
    description=APP_CONFIG.backend.description,
)

app.include_router(search_router)

###############################################################################
create_interface()
ui.run_with(
    app,
    mount_path=APP_CONFIG.ui_runtime.mount_path,
    title=APP_CONFIG.ui_runtime.title,
    show_welcome_message=APP_CONFIG.ui_runtime.show_welcome_message,
    reconnect_timeout=APP_CONFIG.ui_runtime.reconnect_timeout,
)

@app.get("/")
def redirect_to_ui() -> RedirectResponse:
    return RedirectResponse(url=APP_CONFIG.ui_runtime.redirect_path)
