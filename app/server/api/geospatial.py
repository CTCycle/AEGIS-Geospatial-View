from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response

from server.contracts.geospatial import (
    GeospatialCatalogResponse,
    GeospatialCredentialStatusResponse,
    GeospatialLayersResponse,
    GeospatialProviderAccountSetupListResponse,
    GeospatialProviderPayloadResponse,
)
from server.contracts.render_capture import (
    RenderCaptureCreateRequest,
    RenderCaptureResponse,
)
from server.services.geospatial.api_service import (
    GeospatialApiService,
    GeospatialApiServiceError,
    GeospatialCapabilityDisabledError,
    GeospatialCapabilityNotFoundError,
    GeospatialInvalidRequestError,
    GeospatialProviderResponseError,
    GeospatialTileCredentialError,
    GeospatialTileRequestError,
    GeospatialUnsupportedTileError,
)
from server.services.geospatial.render_capture import RenderCaptureStore

router = APIRouter(prefix="/geospatial", tags=["geospatial"])

GEOSPATIAL_ERROR_STATUS = {
    GeospatialCapabilityNotFoundError: status.HTTP_404_NOT_FOUND,
    GeospatialCapabilityDisabledError: status.HTTP_403_FORBIDDEN,
    GeospatialInvalidRequestError: status.HTTP_400_BAD_REQUEST,
    GeospatialUnsupportedTileError: status.HTTP_404_NOT_FOUND,
    GeospatialTileCredentialError: status.HTTP_401_UNAUTHORIZED,
    GeospatialTileRequestError: status.HTTP_502_BAD_GATEWAY,
}

###############################################################################
def get_geospatial_api_service(request: Request) -> GeospatialApiService:
    runtime = getattr(request.app.state, "geospatial_runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Geospatial runtime is not initialized.",
        )
    return runtime.api_service

###############################################################################
def get_render_capture_store(request: Request) -> RenderCaptureStore:
    store = getattr(request.app.state, "render_capture_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Render capture store is not initialized.",
        )
    return store

###############################################################################
def raise_service_http_error(error: GeospatialApiServiceError) -> NoReturn:
    if isinstance(error, GeospatialProviderResponseError):
        raise HTTPException(
            status_code=error.status_code,
            detail={
                "error_code": error.error_code,
                "message": str(error),
            },
        ) from error
    status_code = next(
        (
            mapped_status
            for error_type, mapped_status in GEOSPATIAL_ERROR_STATUS.items()
            if isinstance(error, error_type)
        ),
        None,
    )
    if status_code is not None:
        raise HTTPException(
            status_code=status_code,
            detail=str(error),
        ) from error
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Geospatial service request failed.",
    ) from error

###############################################################################
@router.get(
    "/capabilities",
    response_model=GeospatialCatalogResponse,
    status_code=status.HTTP_200_OK,
)
async def get_geospatial_capabilities(
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> GeospatialCatalogResponse:
    return GeospatialCatalogResponse.model_validate(service.list_capabilities())

###############################################################################
@router.get(
    "/layers",
    response_model=GeospatialLayersResponse,
    status_code=status.HTTP_200_OK,
)
async def get_geospatial_layers(
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> GeospatialLayersResponse:
    return GeospatialLayersResponse.model_validate(service.list_layers())

###############################################################################
@router.get(
    "/layers/{layer_id}/features",
    response_model=GeospatialProviderPayloadResponse,
    status_code=status.HTTP_200_OK,
)
async def get_layer_features(
    layer_id: str,
    bbox: str | None = Query(default=None),
    zoom: int | None = Query(default=None),
    time: str | None = Query(default=None),
    live: bool = Query(default=False),
    incidents: bool = Query(default=False),
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> GeospatialProviderPayloadResponse:
    try:
        return GeospatialProviderPayloadResponse.model_validate(
            await service.get_layer_features(
                layer_id,
                bbox=bbox,
                zoom=zoom,
                time=time,
                live=live,
                incidents=incidents,
            )
        )
    except GeospatialApiServiceError as exc:
        raise_service_http_error(exc)

###############################################################################
@router.get(
    "/layers/{layer_id}/geojson",
    status_code=status.HTTP_200_OK,
)
async def get_layer_geojson(
    layer_id: str,
    bbox: str | None = Query(default=None),
    zoom: int | None = Query(default=None),
    time: str | None = Query(default=None),
    live: bool = Query(default=False),
    incidents: bool = Query(default=False),
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> dict[str, Any]:
    try:
        return await service.get_layer_geojson(
            layer_id,
            bbox=bbox,
            zoom=zoom,
            time=time,
            live=live,
            incidents=incidents,
        )
    except GeospatialApiServiceError as exc:
        raise_service_http_error(exc)

###############################################################################
@router.get(
    "/tiles/{capability_id}/{z}/{x}/{y}.png",
    status_code=status.HTTP_200_OK,
)
async def proxy_capability_tile(
    capability_id: str,
    z: int,
    x: int,
    y: int,
    request: Request,
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> Response:
    try:
        body = await service.fetch_capability_tile(
            capability_id,
            z,
            x,
            y,
            time=request.query_params.get("time"),
        )
    except GeospatialApiServiceError as exc:
        raise_service_http_error(exc)
    return Response(
        content=body,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )

###############################################################################
@router.get(
    "/proxy/tomtom/{kind}/{z}/{x}/{y}.png",
    status_code=status.HTTP_200_OK,
)
async def proxy_tomtom_tile(
    kind: str,
    z: int,
    x: int,
    y: int,
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> Response:
    try:
        body = await service.fetch_tomtom_tile(kind, z, x, y)
    except GeospatialApiServiceError as exc:
        raise_service_http_error(exc)
    return Response(
        content=body,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )

###############################################################################
@router.post(
    "/render-captures",
    response_model=RenderCaptureResponse,
    status_code=status.HTTP_201_CREATED,
)
async def store_render_capture(
    payload: RenderCaptureCreateRequest,
    store: RenderCaptureStore = Depends(get_render_capture_store),
) -> RenderCaptureResponse:
    try:
        store.save(
            run_id=payload.run_id,
            map_session_id=payload.map_session_id,
            collection_revision=payload.collection_revision,
            mime_type=payload.mime_type,
            image_base64=payload.image_base64,
            width=payload.width,
            height=payload.height,
            viewport_bounds=payload.viewport_bounds,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return RenderCaptureResponse(
        run_id=payload.run_id,
        map_session_id=payload.map_session_id,
        collection_revision=payload.collection_revision,
        stored=True,
    )

###############################################################################
@router.get(
    "/cameras",
    response_model=GeospatialProviderPayloadResponse,
    status_code=status.HTTP_200_OK,
)
async def get_geospatial_cameras(
    bbox: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    camera_type: str | None = Query(default=None),
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> GeospatialProviderPayloadResponse:
    try:
        return GeospatialProviderPayloadResponse.model_validate(
            await service.list_cameras(
                bbox=bbox,
                provider=provider,
                camera_type=camera_type,
            )
        )
    except GeospatialApiServiceError as exc:
        raise_service_http_error(exc)

###############################################################################
@router.get(
    "/cameras.geojson",
    status_code=status.HTTP_200_OK,
)
async def get_geospatial_cameras_geojson(
    bbox: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    camera_type: str | None = Query(default=None),
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> dict[str, Any]:
    try:
        return await service.list_cameras_geojson(
            bbox=bbox,
            provider=provider,
            camera_type=camera_type,
        )
    except GeospatialApiServiceError as exc:
        raise_service_http_error(exc)

###############################################################################
@router.get(
    "/sources/{provider_id}/credential-status",
    response_model=GeospatialCredentialStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_credential_status(
    provider_id: str,
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> GeospatialCredentialStatusResponse:
    return GeospatialCredentialStatusResponse.model_validate(
        service.get_credential_status(provider_id)
    )

###############################################################################
@router.get(
    "/providers/account-setup",
    response_model=GeospatialProviderAccountSetupListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_provider_account_setups(
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> GeospatialProviderAccountSetupListResponse:
    return GeospatialProviderAccountSetupListResponse.model_validate(
        service.list_provider_account_setup()
    )
