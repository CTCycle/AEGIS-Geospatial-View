from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from AEGIS.src.server.endpoints.search import router as search_router
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

@app.get("/")
def redirect_to_docs() -> RedirectResponse:
    return RedirectResponse(url="/docs")

