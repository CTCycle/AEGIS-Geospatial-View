from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from AEGIS.app.api.schemas.geographics import AgenticMapRequest, MapRequest
from AEGIS.app.api.schemas.gibs import GIBSImageryPayload
from AEGIS.app.utils.services.agentic import AgenticMapPlanner
from AEGIS.app.utils.services.geographics import GIBSClient

router = APIRouter(tags=["maps"])
gibs_client = GIBSClient()
agentic_planner = AgenticMapPlanner()


###############################################################################
def build_map_response(
    payload: GIBSImageryPayload, message: str | None = None
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "kvp_url": payload.kvp_url,
        "layer": payload.layer.layer_identifier,
        "tile": {
            "zoom": payload.tile.zoom,
            "row": payload.tile.row,
            "column": payload.tile.column,
        },
        "location": {
            "latitude": payload.location.latitude,
            "longitude": payload.location.longitude,
            "source": payload.location.source,
            "reference": payload.location.reference,
        },
        "projection": payload.request.projection,
        "tile_matrix_set": payload.request.tile_matrix_set,
        "time": payload.request.time,
    }
    return {
        "image": {
            "url": payload.image_url,
            "caption": payload.caption,
        },
        "request": payload.request.model_dump(),
        "message": message or payload.message,
        "metadata": metadata,
    }


###############################################################################
@router.post("/maps/search", status_code=status.HTTP_200_OK)
@router.post("/maps", status_code=status.HTTP_200_OK)
async def render_map(request: MapRequest) -> dict[str, Any]:
    try:
        payload = gibs_client.build_imagery_payload(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return build_map_response(payload)


###############################################################################
@router.post("/maps/agentic", status_code=status.HTTP_200_OK)
async def render_agentic_map(request: AgenticMapRequest) -> dict[str, Any]:
    try:
        plan = agentic_planner.build_plan(request)
        payload = gibs_client.build_imagery_payload(plan.map_request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    message = agentic_planner.compose_status_message(request, payload.message, plan.notes)
    response = build_map_response(payload, message)
    metadata = response.setdefault("metadata", {})
    metadata["agentic"] = {
        "query": request.query,
        "agent_model": request.agent_model,
        "temperature": request.temperature,
        "use_cloud_models": request.use_cloud_models,
        "cloud_model": request.openai_model,
        "notes": plan.notes,
        "inferred": plan.metadata,
    }
    return response

