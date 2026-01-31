from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from AEGIS.server.utils.constants import DOCS_ROUTE, ROOT_ROUTE
from AEGIS.server.utils.variables import env_variables
from AEGIS.server.routes.search import router as search_router
from AEGIS.server.routes.browser import router as browser_router
from AEGIS.server.configurations import server_settings

###############################################################################
app = FastAPI(
    title=server_settings.fastapi.title,
    version=server_settings.fastapi.version,
    description=server_settings.fastapi.description,
)

app.include_router(search_router)
app.include_router(browser_router)


@app.get(ROOT_ROUTE)
def redirect_to_docs() -> RedirectResponse:
    return RedirectResponse(url=DOCS_ROUTE)
