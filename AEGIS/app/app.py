from __future__ import annotations

from AEGIS.app.variables import EnvironmentVariables

EV = EnvironmentVariables()

import os

import gradio as gr
from fastapi import FastAPI

from AEGIS.app.api.endpoints.agent import router as report_router
from AEGIS.app.api.endpoints.ollama import router as models_router
from AEGIS.app.api.endpoints.pharmacology import router as pharma_router
from AEGIS.app.client.main import create_interface
from AEGIS.app.logger import logger
from AEGIS.app.utils.database.sqlite import database

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
app.include_router(pharma_router)

ui_app = create_interface()
app = gr.mount_gradio_app(app, ui_app, path="/ui", root_path="/ui")
