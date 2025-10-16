from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from AEGIS.app.api.schemas.geographics import MapRequest
from AEGIS.app.utils.services.geographics import GIBSClient

router = APIRouter(tags=["maps"])
gibs_client = GIBSClient()


###############################################################################
@router.post("/maps", status_code=status.HTTP_200_OK)
async def render_map(request: MapRequest) -> dict[str, Any]:
    try:
        payload = gibs_client.build_imagery_payload(request)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

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
        "message": payload.message,
        "metadata": metadata,
    }

