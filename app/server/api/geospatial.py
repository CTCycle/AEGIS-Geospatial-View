from __future__ import annotations

import os
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from server.domain.geographics import (
    ProviderAccountSetup,
    ProviderCredentialValidationRequest,
    ProviderCredentialValidationResult,
)
from server.services.geospatial.catalog import GeospatialCatalogService
from server.services.geospatial.layer_auditor import audit_all_manifests
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.provider_account_setup_service import (
    ProviderAccountSetupService,
)
from server.services.geospatial.provider_credential_validation_service import (
    ProviderCredentialValidationService,
)
from server.services.geospatial.provider_registry import (
    ProviderNotRegisteredError,
    ProviderRegistry,
)
from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderCircuitOpenError,
    ProviderError,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.tomtom import build_tomtom_tile_url
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
    live: bool = Query(default=False),
    incidents: bool = Query(default=False),
) -> dict[str, Any]:
    manifest = _manifest_by_id(layer_id)
    provider_id = str(manifest.get("provider") or "")
    params: dict[str, Any] = {}
    if live:
        params["live"] = True
    if incidents:
        params["incidents"] = True
    request = ProviderRequest(
        capability_id=layer_id,
        bbox=_parse_bbox(bbox),
        zoom=zoom,
        time=_parse_time(time),
        params=params,
    )
    return await _fetch_provider_payload(provider_id, request)


@router.get(
    "/proxy/tomtom/{kind}/{z}/{x}/{y}.png",
    status_code=status.HTTP_200_OK,
)
async def proxy_tomtom_tile(kind: str, z: int, x: int, y: int) -> Response:
    if kind not in {"basic", "traffic-flow"}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unsupported TomTom tile type.",
        )
    api_key = os.getenv("TOMTOM_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TomTom API key is required.",
        )
    url = build_tomtom_tile_url(kind, z, x, y, api_key)
    try:
        body = await _fetch_binary_url(url)
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="TomTom rejected the configured API key.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"TomTom tile request failed with HTTP {exc.code}.",
        ) from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="TomTom tile request failed.",
        ) from exc
    return Response(
        content=body,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=60"},
    )


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
        params={"live": True, **({"camera_type": camera_type} if camera_type else {})},
    )
    return await _fetch_provider_payload(provider_id, request)


@router.get("/cameras/{camera_id:path}", status_code=status.HTTP_200_OK)
async def get_geospatial_camera(camera_id: str) -> dict[str, Any]:
    provider_id, provider_camera_id = _parse_camera_identifier(camera_id)
    if provider_id:
        request = ProviderRequest(
            capability_id=provider_id,
            params={"live": True, "camera_id": provider_camera_id},
        )
        listing = await _fetch_provider_payload(provider_id, request)
        if listing.get("status") != "ok":
            return {
                "id": camera_id,
                "status": listing.get("status", "metadata-unavailable"),
                "provider": provider_id,
                "message": listing.get("message")
                or "Camera detail lookup is not available.",
            }
        payload = listing.get("payload")
        features = payload.get("features") if isinstance(payload, dict) else None
        if isinstance(features, list):
            for feature in features:
                if not isinstance(feature, dict):
                    continue
                feature_id = str(feature.get("id") or "")
                if feature_id in {camera_id, provider_camera_id}:
                    return {
                        "id": camera_id,
                        "status": "ok",
                        "provider": provider_id,
                        "camera": feature,
                        "attribution": listing.get("attribution", []),
                        "warnings": listing.get("warnings", []),
                        "stale": listing.get("stale", False),
                    }
    return {
        "id": camera_id,
        "status": "metadata-unavailable",
        "provider": provider_id or "unknown",
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


@router.get(
    "/providers/account-setup",
    response_model=list[ProviderAccountSetup],
    status_code=status.HTTP_200_OK,
)
async def list_provider_account_setups() -> list[ProviderAccountSetup]:
    return ProviderAccountSetupService().list_setups()


@router.get(
    "/providers/{provider_id}/account-setup",
    response_model=ProviderAccountSetup,
    status_code=status.HTTP_200_OK,
)
async def get_provider_account_setup(provider_id: str) -> ProviderAccountSetup:
    try:
        return ProviderAccountSetupService().get_setup(provider_id)
    except ProviderNotRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/providers/{provider_id}/credentials/validate",
    response_model=ProviderCredentialValidationResult,
    status_code=status.HTTP_200_OK,
)
async def validate_provider_credentials(
    provider_id: str,
    request: ProviderCredentialValidationRequest,
) -> ProviderCredentialValidationResult:
    credentials = {
        key: value.get_secret_value()
        for key, value in request.credentials.items()
    }
    try:
        return await ProviderCredentialValidationService().validate(
            provider_id, credentials
        )
    except ProviderNotRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


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
    except ProviderRateLimitError as exc:
        return {
            "status": "rate-limited",
            "provider": provider_id,
            "message": str(exc),
        }
    except (
        ProviderNotRegisteredError,
        ProviderUnavailableError,
        ProviderTimeoutError,
        ProviderCircuitOpenError,
        ProviderError,
    ) as exc:
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


def _parse_camera_identifier(camera_id: str) -> tuple[str | None, str]:
    normalized = camera_id.strip()
    for separator in ("/", ":"):
        if separator in normalized:
            provider_id, provider_camera_id = normalized.split(separator, 1)
            provider_id = provider_id.strip()
            provider_camera_id = provider_camera_id.strip()
            if provider_id and provider_camera_id:
                return provider_id, provider_camera_id
    return None, normalized


def _provider_requires_credentials(provider_id: str) -> bool:
    payload = GeospatialManifestLoader().load_all()
    for item in payload.get("providers") or []:
        if str(item.get("id") or "") == provider_id:
            auth = item.get("auth")
            return bool(isinstance(auth, dict) and auth.get("required"))
    return provider_id in RuntimeRegistry.CREDENTIAL_ENV_BY_PROVIDER


async def _fetch_binary_url(url: str) -> bytes:
    import asyncio

    return await asyncio.to_thread(_fetch_binary_url_sync, url)


def _fetch_binary_url_sync(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "AEGIS/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()
