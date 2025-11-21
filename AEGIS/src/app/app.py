from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from nicegui import ui

from AEGIS.src.app.server.endpoints.search import router as search_router
from AEGIS.src.app.client.interface import create_interface
from AEGIS.src.packages.configurations import configurations


###############################################################################
fastapi_settings = configurations.server.fastapi
ui_settings = configurations.client.ui

app = FastAPI(
    title=fastapi_settings.title,
    version=fastapi_settings.version,
    description=fastapi_settings.description,
)

app.include_router(search_router)

create_interface()
ui.run_with(
    app,
    mount_path=ui_settings.mount_path,
    title=ui_settings.title,
    show_welcome_message=ui_settings.show_welcome_message,
    reconnect_timeout=ui_settings.reconnect_timeout,
)

@app.get("/")
def redirect_to_ui() -> RedirectResponse:
    return RedirectResponse(url=ui_settings.redirect_path)
