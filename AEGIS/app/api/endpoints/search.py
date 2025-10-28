from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from AEGIS.app.api.schemas.geographics import LocationSearchRequest


router = APIRouter(prefix="/maps", tags=["search"])


###############################################################################
@router.post("/search", status_code=status.HTTP_200_OK)
async def search_by_location(payload: LocationSearchRequest) -> dict[str, Any]:
    return {
        "message": "Location search request received.",
        "payload": payload.as_query_payload(),
    }


###############################################################################
@router.post("/agentic", status_code=status.HTTP_202_ACCEPTED)
async def search_by_agent() -> dict[str, str]:
    return {"message": "Agentic search endpoint is not implemented yet."}


