from __future__ import annotations

from AEGIS.app.variables import env_variables

import os
from fastapi import FastAPI
from nicegui import ui

from AEGIS.app.api.endpoints.search import router as report_router
from AEGIS.app.api.endpoints.filters import router as models_router
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
    title="LLM Backend",
    version="0.1.0",
    description="Minimal FastAPI bootstrap with chat, embeddings, and a placeholder endpoint.",
)

app.include_router(report_router)
app.include_router(models_router)

create_interface()
ui.run_with(app, mount_path="/ui", title="AEGIS Geographics")
