from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response

from server.domain.geographics import (
    GeospatialCameraDetailResponse,
    GeospatialCatalogResponse,
    GeospatialCredentialStatusResponse,
    GeospatialLayerHealthResponse,
    GeospatialLayersResponse,
    GeospatialProviderAccountSetupListResponse,
    GeospatialProviderAccountSetupResponse,
    GeospatialProviderPayloadResponse,
    LayerAuditReport,
)
from server.services.geospatial.composition import build_geospatial_runtime
from server.services.geospatial.api_service import (
    GeospatialApiService,
    GeospatialApiServiceError,
    GeospatialCapabilityNotFoundError,
    GeospatialInvalidRequestError,
    GeospatialTileCredentialError,
    GeospatialTileRequestError,
    GeospatialUnsupportedTileError,
)

router = APIRouter(prefix="/geospatial", tags=["geospatial"])

GEOSPATIAL_ERROR_STATUS = {
    GeospatialCapabilityNotFoundError: status.HTTP_404_NOT_FOUND,
    GeospatialInvalidRequestError: status.HTTP_400_BAD_REQUEST,
    GeospatialUnsupportedTileError: status.HTTP_404_NOT_FOUND,
    GeospatialTileCredentialError: status.HTTP_401_UNAUTHORIZED,
    GeospatialTileRequestError: status.HTTP_502_BAD_GATEWAY,
}


def get_geospatial_api_service(request: Request) -> GeospatialApiService:
    runtime = getattr(request.app.state, "geospatial_runtime", None)
    if runtime is None:
        runtime = build_geospatial_runtime()
        request.app.state.geospatial_runtime = runtime
    return runtime.api_service


def raise_service_http_error(error: GeospatialApiServiceError) -> NoReturn:
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


@router.get(
    "/capabilities",
    response_model=GeospatialCatalogResponse,
    status_code=status.HTTP_200_OK,
)
async def get_geospatial_capabilities(
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> GeospatialCatalogResponse:
    return GeospatialCatalogResponse.model_validate(service.list_capabilities())


@router.get(
    "/layers",
    response_model=GeospatialLayersResponse,
    status_code=status.HTTP_200_OK,
)
async def get_geospatial_layers(
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> GeospatialLayersResponse:
    return GeospatialLayersResponse.model_validate(service.list_layers())


@router.get(
    "/layers/{layer_id}/health",
    response_model=GeospatialLayerHealthResponse,
    status_code=status.HTTP_200_OK,
)
async def get_layer_health(
    layer_id: str,
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> GeospatialLayerHealthResponse:
    try:
        return GeospatialLayerHealthResponse.model_validate(
            service.get_layer_health(layer_id)
        )
    except GeospatialApiServiceError as exc:
        raise_service_http_error(exc)


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
) -> dict:
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


@router.get(
    "/tiles/{capability_id}/{z}/{x}/{y}.png",
    status_code=status.HTTP_200_OK,
)
async def proxy_capability_tile(
    capability_id: str,
    z: int,
    x: int,
    y: int,
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> Response:
    try:
        body = await service.fetch_capability_tile(capability_id, z, x, y)
    except GeospatialApiServiceError as exc:
        raise_service_http_error(exc)
    return Response(
        content=body,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )


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


@router.get(
    "/cameras.geojson",
    status_code=status.HTTP_200_OK,
)
async def get_geospatial_cameras_geojson(
    bbox: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    camera_type: str | None = Query(default=None),
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> dict:
    try:
        return await service.list_cameras_geojson(
            bbox=bbox,
            provider=provider,
            camera_type=camera_type,
        )
    except GeospatialApiServiceError as exc:
        raise_service_http_error(exc)


@router.get(
    "/cameras/{camera_id:path}",
    response_model=GeospatialCameraDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_geospatial_camera(
    camera_id: str,
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> GeospatialCameraDetailResponse:
    return GeospatialCameraDetailResponse.model_validate(
        await service.get_camera(camera_id)
    )


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


@router.get(
    "/providers/{provider_id}/account-setup",
    response_model=GeospatialProviderAccountSetupResponse,
    status_code=status.HTTP_200_OK,
)
async def get_provider_account_setup(
    provider_id: str,
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> GeospatialProviderAccountSetupResponse:
    try:
        return GeospatialProviderAccountSetupResponse.model_validate(
            service.get_provider_account_setup(provider_id)
        )
    except GeospatialApiServiceError as exc:
        raise_service_http_error(exc)


@router.post(
    "/audit",
    response_model=LayerAuditReport,
    status_code=status.HTTP_200_OK,
)
async def audit_geospatial_sources(
    service: GeospatialApiService = Depends(get_geospatial_api_service),
) -> LayerAuditReport:
    return service.audit_sources()
