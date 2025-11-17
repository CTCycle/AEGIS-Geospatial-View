from __future__ import annotations


from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from nicegui import ui

from AEGIS.src.app.backend.endpoints.search import router as search_router
from AEGIS.src.app.frontend.interface import create_interface
from AEGIS.src.packages.configurations import configurations
from AEGIS.src.packages.logger import logger
from AEGIS.src.packages.utils.repository.database import database


###############################################################################
if database.requires_sqlite_initialization():
    logger.info("Database not found, creating instance and making all tables")
    database.initialize_database()
    logger.info("AEGIS database has been initialized successfully.")

app = FastAPI(
    title=configurations.backend.title,
    version=configurations.backend.version,
    description=configurations.backend.description,
)

app.include_router(search_router)

###############################################################################
create_interface()
ui.run_with(
    app,
    mount_path=configurations.ui_runtime.mount_path,
    title=configurations.ui_runtime.title,
    show_welcome_message=configurations.ui_runtime.show_welcome_message,
    reconnect_timeout=configurations.ui_runtime.reconnect_timeout,
)


@app.get("/")
def redirect_to_ui() -> RedirectResponse:
    return RedirectResponse(url=configurations.ui_runtime.redirect_path)
