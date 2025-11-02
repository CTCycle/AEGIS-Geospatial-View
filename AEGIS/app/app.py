from __future__ import annotations

from AEGIS.app.variables import env_variables

import os
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from nicegui import ui

from AEGIS.app.api.endpoints.search import router as search_router
from AEGIS.app.client.interface import create_interface
from AEGIS.app.logger import logger
from AEGIS.app.utils.repository.database import database

###############################################################################
# initialize the database if it has not been created
if not os.path.exists(database.db_path):
    logger.info("Database not found, creating instance and making all tables")
    database.initialize_database()
    logger.info("AEGIS database has been initialized successfully.")

app = FastAPI(
    title="AEGIS Geospatial Search Backend",
    version="0.1.0",
    description="FastAPI backend",
)

app.include_router(search_router)

create_interface()
ui.run_with(
    app,
    mount_path="/ui",
    title="AEGIS Geospatial Search",
    show_welcome_message=False,
    reconnect_timeout=180,
)


@app.get("/")
def redirect_to_ui() -> RedirectResponse:
    return RedirectResponse(url="/ui")
