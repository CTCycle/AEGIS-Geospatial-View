from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from AEGIS.server.packages.variables import env_variables
from AEGIS.server.endpoints.search import router as search_router
from AEGIS.server.packages.configurations import server_settings

###############################################################################
app = FastAPI(
    title=server_settings.fastapi.title,
    version=server_settings.fastapi.version,
    description=server_settings.fastapi.description,
)

app.include_router(search_router)

@app.get("/")
def redirect_to_docs() -> RedirectResponse:
    return RedirectResponse(url="/docs")

