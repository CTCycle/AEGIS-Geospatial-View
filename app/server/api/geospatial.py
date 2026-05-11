from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from server.services.geospatial.catalog import GeospatialCatalogService
from server.services.geospatial.layer_auditor import audit_all_manifests
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.provider_registry import (
    ProviderNotRegisteredError,
    ProviderRegistry,
)
from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderRequest,
    ProviderUnavailableError,
)
from server.services.geospatial.runtime_registry import RuntimeRegistry

router = APIRouter(prefix="/geospatial", tags=["geospatial"])


@router.get("/capabilities", status_code=status.HTTP_200_OK)
async def get_geospatial_capabilities() -> dict[str, Any]:
    return GeospatialCatalogService().list_catalog()


@router.get("/layers", status_code=status.HTTP_200_OK)
async def get_geospatial_layers() -> dict[str, Any]:
    catalog = GeospatialCatalogService().list_catalog()
    return {
        "basemaps": catalog["basemaps"],
        "overlays": catalog["overlays"],
        "cameras": catalog.get("cameras", []),
        "transit": catalog.get("transit", []),
    }


@router.get("/layers/{layer_id}/health", status_code=status.HTTP_200_OK)
async def get_layer_health(layer_id: str) -> dict[str, Any]:
    manifest = _manifest_by_id(layer_id)
    reliability = manifest.get("reliability")
    return {
        "id": layer_id,
        "provider": manifest.get("provider"),
        "reliability": reliability if isinstance(reliability, dict) else {},
        "runtime": RuntimeRegistry().provider_health(layer_id),
    }


@router.get("/layers/{layer_id}/features", status_code=status.HTTP_200_OK)
async def get_layer_features(
    layer_id: str,
    bbox: str | None = Query(default=None),
    zoom: int | None = Query(default=None),
    time: str | None = Query(default=None),
) -> dict[str, Any]:
    manifest = _manifest_by_id(layer_id)
    provider_id = str(manifest.get("provider") or "")
    request = ProviderRequest(
        capability_id=layer_id,
        bbox=_parse_bbox(bbox),
        zoom=zoom,
        time=_parse_time(time),
    )
    return await _fetch_provider_payload(provider_id, request)


@router.get("/cameras", status_code=status.HTTP_200_OK)
async def get_geospatial_cameras(
    bbox: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    camera_type: str | None = Query(default=None),
) -> dict[str, Any]:
    provider_id = provider or "windy_webcams"
    request = ProviderRequest(
        capability_id=provider_id,
        bbox=_parse_bbox(bbox),
        params={"camera_type": camera_type} if camera_type else {},
    )
    return await _fetch_provider_payload(provider_id, request)


@router.get("/cameras/{camera_id}", status_code=status.HTTP_200_OK)
async def get_geospatial_camera(camera_id: str) -> dict[str, Any]:
    return {
        "id": camera_id,
        "status": "metadata-unavailable",
        "message": "Camera detail lookup requires a configured camera provider response.",
    }


@router.get("/sources/{provider_id}/credential-status", status_code=status.HTTP_200_OK)
async def get_credential_status(provider_id: str) -> dict[str, Any]:
    env_name = RuntimeRegistry.CREDENTIAL_ENV_BY_PROVIDER.get(provider_id)
    configured = bool(env_name and os.getenv(env_name, "").strip())
    return {
        "provider": provider_id,
        "required": _provider_requires_credentials(provider_id),
        "configured": configured,
        "environmentVariable": env_name,
    }


@router.post("/audit", status_code=status.HTTP_200_OK)
async def audit_geospatial_sources() -> dict[str, Any]:
    return audit_all_manifests(strict=True).model_dump()


def _manifest_by_id(capability_id: str) -> dict[str, Any]:
    payload = GeospatialManifestLoader().load_all()
    for collection_name in ("basemaps", "overlays", "cameras", "transit", "tools", "providers"):
        for item in payload.get(collection_name) or []:
            if str(item.get("id") or "") == capability_id:
                return dict(item)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Geospatial capability '{capability_id}' was not found.",
    )


async def _fetch_provider_payload(
    provider_id: str, request: ProviderRequest
) -> dict[str, Any]:
    registry = ProviderRegistry()
    registry.build_from_manifests()
    try:
        response = await registry.fetch(provider_id, request)
    except ProviderAuthError as exc:
        return {
            "status": "missing-credential",
            "provider": provider_id,
            "message": str(exc),
        }
    except (ProviderNotRegisteredError, ProviderUnavailableError) as exc:
        return {
            "status": "unavailable",
            "provider": provider_id,
            "message": str(exc),
        }
    return {
        "status": "ok",
        "provider": provider_id,
        "payload": response.payload,
        "attribution": response.attribution,
        "warnings": response.warnings,
        "stale": response.stale,
    }


def _parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    try:
        parts = tuple(float(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bbox must be four comma-separated numbers.",
        ) from exc
    if len(parts) != 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="bbox must be four comma-separated numbers.",
        )
    return parts  # type: ignore[return-value]


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="time must be ISO-8601.",
        ) from exc


def _provider_requires_credentials(provider_id: str) -> bool:
    payload = GeospatialManifestLoader().load_all()
    for item in payload.get("providers") or []:
        if str(item.get("id") or "") == provider_id:
            auth = item.get("auth")
            return bool(isinstance(auth, dict) and auth.get("required"))
    return provider_id in RuntimeRegistry.CREDENTIAL_ENV_BY_PROVIDER
