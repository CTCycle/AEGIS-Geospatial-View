from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from AEGIS.server.domain.access_keys import (
    AccessKeyCreateRequest,
    AccessKeyDeleteResponse,
    AccessKeyResponse,
)
from AEGIS.server.services.access_keys import (
    AccessKeyNotFoundError,
    AccessKeysService,
    AccessKeyServiceError,
    AccessKeyValidationError,
)

router = APIRouter(prefix="/access-keys", tags=["access-keys"])


def get_access_keys_service(request: Request) -> AccessKeysService:
    return request.app.state.access_keys_service


@router.get("", response_model=list[AccessKeyResponse], status_code=status.HTTP_200_OK)
def list_access_keys(
    provider: str = Query(..., min_length=1),
    access_keys_service: AccessKeysService = Depends(get_access_keys_service),
) -> list[AccessKeyResponse]:
    try:
        return access_keys_service.list_keys(provider)
    except AccessKeyValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post("", response_model=AccessKeyResponse, status_code=status.HTTP_201_CREATED)
def create_access_key(
    payload: AccessKeyCreateRequest,
    access_keys_service: AccessKeysService = Depends(get_access_keys_service),
) -> AccessKeyResponse:
    try:
        return access_keys_service.create_key(payload.provider, payload.access_key)
    except AccessKeyValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AccessKeyServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.put(
    "/{key_id}/activate",
    response_model=AccessKeyResponse,
    status_code=status.HTTP_200_OK,
)
def activate_access_key(
    key_id: int,
    provider: str = Query(..., min_length=1),
    access_keys_service: AccessKeysService = Depends(get_access_keys_service),
) -> AccessKeyResponse:
    try:
        return access_keys_service.activate_key(key_id, provider)
    except AccessKeyValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AccessKeyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{key_id}",
    response_model=AccessKeyDeleteResponse,
    status_code=status.HTTP_200_OK,
)
def delete_access_key(
    key_id: int,
    provider: str = Query(..., min_length=1),
    access_keys_service: AccessKeysService = Depends(get_access_keys_service),
) -> AccessKeyDeleteResponse:
    try:
        access_keys_service.delete_key(key_id, provider)
        return AccessKeyDeleteResponse(success=True)
    except AccessKeyValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AccessKeyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc