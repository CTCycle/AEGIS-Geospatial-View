from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from server.contracts.settings import (
    RuntimeSettingsResponse,
    RuntimeSettingsUpdateRequest,
)
from server.contracts.database_settings import (
    DatabaseConnectionTestResponse,
    DatabaseSettingsRequest,
    DatabaseSettingsResponse,
)
from server.services.database_runtime import (
    DatabaseConnectionError,
    DatabaseRuntimeBusyError,
    DatabaseRuntimeManager,
    DatabaseRuntimeSwitchError,
    database_settings_response,
)
from server.services.settings.runtime_settings import RuntimeSettingsService


router = APIRouter(prefix="/settings", tags=["settings"])


def get_database_runtime_manager(request: Request) -> DatabaseRuntimeManager:
    manager = getattr(request.app.state, "database_runtime_manager", None)
    if not isinstance(manager, DatabaseRuntimeManager):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database settings service is unavailable.",
        )
    return manager


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


@router.get(
    "/database",
    response_model=DatabaseSettingsResponse,
    status_code=status.HTTP_200_OK,
)
def get_database_settings(
    manager: DatabaseRuntimeManager = Depends(get_database_runtime_manager),
) -> DatabaseSettingsResponse:
    return database_settings_response(manager.configuration)


@router.post(
    "/database/test",
    response_model=DatabaseConnectionTestResponse,
    status_code=status.HTTP_200_OK,
)
async def test_database_connection(
    payload: DatabaseSettingsRequest,
    manager: DatabaseRuntimeManager = Depends(get_database_runtime_manager),
) -> DatabaseConnectionTestResponse:
    try:
        return await manager.test_connection(payload.as_configuration())
    except DatabaseConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.put(
    "/database",
    response_model=DatabaseSettingsResponse,
    status_code=status.HTTP_200_OK,
)
async def switch_database(
    payload: DatabaseSettingsRequest,
    manager: DatabaseRuntimeManager = Depends(get_database_runtime_manager),
) -> DatabaseSettingsResponse:
    try:
        return await manager.switch_database(payload.as_configuration())
    except DatabaseConnectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except DatabaseRuntimeBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except DatabaseRuntimeSwitchError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
