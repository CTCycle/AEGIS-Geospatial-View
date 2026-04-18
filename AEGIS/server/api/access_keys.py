from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from AEGIS.server.domain.access_keys import (
    AccessKeyCreateRequest,
    AccessKeyDeleteResponse,
    AccessKeyResponse,
)
from AEGIS.server.repositories.serialization.access_keys import AccessKeySerializer

router = APIRouter(prefix="/access-keys", tags=["access-keys"])
serializer = AccessKeySerializer()


def _to_response(row) -> AccessKeyResponse:  # noqa: ANN001
    return AccessKeyResponse(
        id=row.id,
        provider=row.provider,
        is_active=row.is_active,
        fingerprint=row.fingerprint,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_used_at=row.last_used_at,
    )


@router.get("", response_model=list[AccessKeyResponse], status_code=status.HTTP_200_OK)
def list_access_keys(
    provider: str = Query(..., min_length=1),
) -> list[AccessKeyResponse]:
    try:
        rows = serializer.list_keys(provider)
        return [_to_response(row) for row in rows]
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("", response_model=AccessKeyResponse, status_code=status.HTTP_201_CREATED)
def create_access_key(payload: AccessKeyCreateRequest) -> AccessKeyResponse:
    try:
        row = serializer.create_key(payload.provider, payload.access_key)
        return _to_response(row)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


@router.put(
    "/{key_id}/activate",
    response_model=AccessKeyResponse,
    status_code=status.HTTP_200_OK,
)
def activate_access_key(
    key_id: int,
    provider: str = Query(..., min_length=1),
) -> AccessKeyResponse:
    try:
        row = serializer.activate_key(key_id, provider)
        return _to_response(row)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.delete(
    "/{key_id}", response_model=AccessKeyDeleteResponse, status_code=status.HTTP_200_OK
)
def delete_access_key(
    key_id: int,
    provider: str = Query(..., min_length=1),
) -> AccessKeyDeleteResponse:
    try:
        serializer.delete_key(key_id, provider)
        return AccessKeyDeleteResponse(success=True)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
