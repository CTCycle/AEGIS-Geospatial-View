from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from server.contracts.settings import (
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
)
from server.services.settings.runtime_settings import RuntimeSettingsService


router = APIRouter(prefix="/settings", tags=["settings"])


def get_runtime_settings_service(request: Request) -> RuntimeSettingsService:
    service = getattr(request.app.state, "runtime_settings_service", None)
    if not isinstance(service, RuntimeSettingsService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Runtime settings service is unavailable.",
        )
    return service


@router.get(
    "/runtime",
    response_model=RuntimeSettingsResponse,
    status_code=status.HTTP_200_OK,
)
def get_runtime_settings(
    service: RuntimeSettingsService = Depends(get_runtime_settings_service),
) -> RuntimeSettingsResponse:
    try:
        return service.get_settings()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.patch(
    "/runtime",
    response_model=RuntimeSettingsResponse,
    status_code=status.HTTP_200_OK,
)
def update_runtime_settings(
    payload: RuntimeSettingsUpdateRequest,
    service: RuntimeSettingsService = Depends(get_runtime_settings_service),
) -> RuntimeSettingsResponse:
    try:
        return service.update_settings(payload.as_patch())
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
