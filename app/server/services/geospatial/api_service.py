from __future__ import annotations

import asyncio
import os
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

from server.domain.geographics import LayerAuditReport
from server.services.geospatial.catalog import GeospatialCatalogService
from server.services.geospatial.layer_auditor import audit_all_manifests
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
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


class GeospatialApiServiceError(Exception):
    """Base exception for geospatial API service failures."""


class GeospatialCapabilityNotFoundError(GeospatialApiServiceError):
    """Raised when a requested manifest capability does not exist."""


class GeospatialInvalidRequestError(GeospatialApiServiceError):
    """Raised when query parameters cannot be parsed safely."""


class GeospatialTileCredentialError(GeospatialApiServiceError):
    """Raised when a tile provider credential is missing or rejected."""


class GeospatialTileRequestError(GeospatialApiServiceError):
    """Raised when a tile provider request fails."""


class GeospatialUnsupportedTileError(GeospatialApiServiceError):
    """Raised when a tile kind is not supported."""


class GeospatialApiService:
    def __init__(
        self,
        *,
        catalog_service: GeospatialCatalogService | None = None,
        manifest_loader: GeospatialManifestLoader | None = None,
        runtime_registry: RuntimeRegistry | None = None,
        provider_registry: ProviderRegistry | None = None,
    ) -> None:
        self.catalog_service = catalog_service or GeospatialCatalogService()
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self.runtime_registry = runtime_registry or RuntimeRegistry()
        self.provider_registry = provider_registry or ProviderRegistry()

    def list_capabilities(self) -> dict[str, list[dict[str, Any]]]:
        return self.catalog_service.list_catalog()

    def list_layers(self) -> dict[str, list[dict[str, Any]]]:
        catalog = self.catalog_service.list_catalog()
        return {
            "basemaps": catalog["basemaps"],
            "overlays": catalog["overlays"],
            "cameras": catalog.get("cameras", []),
            "transit": catalog.get("transit", []),
        }

    def get_layer_health(self, layer_id: str) -> dict[str, Any]:
        manifest = self._manifest_by_id(layer_id)
        reliability = manifest.get("reliability")
        return {
            "id": layer_id,
            "provider": manifest.get("provider"),
            "reliability": reliability if isinstance(reliability, dict) else {},
            "runtime": self.runtime_registry.provider_health(layer_id),
        }

    async def get_layer_features(
        self,
        layer_id: str,
        *,
        bbox: str | None,
        zoom: int | None,
        time: str | None,
        live: bool,
        incidents: bool,
    ) -> dict[str, Any]:
        manifest = self._manifest_by_id(layer_id)
        provider_id = str(manifest.get("provider") or "")
        params: dict[str, Any] = {}
        if live:
            params["live"] = True
        if incidents:
            params["incidents"] = True
        request = ProviderRequest(
            capability_id=layer_id,
            bbox=self._parse_bbox(bbox),
            zoom=zoom,
            time=self._parse_time(time),
            params=params,
        )
        return await self._fetch_provider_payload(provider_id, request)

    async def fetch_tomtom_tile(self, kind: str, z: int, x: int, y: int) -> bytes:
        if kind not in {"basic", "traffic-flow"}:
            raise GeospatialUnsupportedTileError("Unsupported TomTom tile type.")
        api_key = os.getenv("TOMTOM_API_KEY", "").strip()
        if not api_key:
            raise GeospatialTileCredentialError("TomTom API key is required.")
        url = build_tomtom_tile_url(kind, z, x, y, api_key)
        try:
            return await self._fetch_binary_url(url)
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise GeospatialTileCredentialError(
                    "TomTom rejected the configured API key."
                ) from exc
            raise GeospatialTileRequestError(
                f"TomTom tile request failed with HTTP {exc.code}."
            ) from exc
        except (TimeoutError, urllib.error.URLError) as exc:
            raise GeospatialTileRequestError("TomTom tile request failed.") from exc

    async def list_cameras(
        self,
        *,
        bbox: str | None,
        provider: str | None,
        camera_type: str | None,
    ) -> dict[str, Any]:
        provider_id = provider or "windy_webcams"
        request = ProviderRequest(
            capability_id=provider_id,
            bbox=self._parse_bbox(bbox),
            params={"live": True, **({"camera_type": camera_type} if camera_type else {})},
        )
        return await self._fetch_provider_payload(provider_id, request)

    async def get_camera(self, camera_id: str) -> dict[str, Any]:
        provider_id, provider_camera_id = self._parse_camera_identifier(camera_id)
        if provider_id:
            request = ProviderRequest(
                capability_id=provider_id,
                params={"live": True, "camera_id": provider_camera_id},
            )
            listing = await self._fetch_provider_payload(provider_id, request)
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

    def get_credential_status(self, provider_id: str) -> dict[str, Any]:
        env_name = RuntimeRegistry.CREDENTIAL_ENV_BY_PROVIDER.get(provider_id)
        configured = bool(env_name and os.getenv(env_name, "").strip())
        return {
            "provider": provider_id,
            "required": self._provider_requires_credentials(provider_id),
            "configured": configured,
            "environmentVariable": env_name,
        }

    def list_provider_account_setup(self) -> dict[str, list[dict[str, Any]]]:
        payload = self.manifest_loader.load_all()
        providers = [
            self._build_provider_account_setup(item)
            for item in payload.get("providers") or []
            if isinstance(item, dict)
        ]
        providers.sort(key=lambda item: str(item.get("name") or item.get("provider_id")))
        return {"providers": providers}

    def get_provider_account_setup(self, provider_id: str) -> dict[str, Any]:
        payload = self.manifest_loader.load_all()
        for item in payload.get("providers") or []:
            if isinstance(item, dict) and str(item.get("id") or "") == provider_id:
                return self._build_provider_account_setup(item)
        raise GeospatialCapabilityNotFoundError(
            f"Geospatial provider '{provider_id}' was not found."
        )

    def audit_sources(self) -> LayerAuditReport:
        return audit_all_manifests(strict=True)

    def _manifest_by_id(self, capability_id: str) -> dict[str, Any]:
        payload = self.manifest_loader.load_all()
        collection_names = (
            "basemaps",
            "overlays",
            "cameras",
            "transit",
            "tools",
            "providers",
        )
        for collection_name in collection_names:
            for item in payload.get(collection_name) or []:
                if str(item.get("id") or "") == capability_id:
                    return dict(item)
        raise GeospatialCapabilityNotFoundError(
            f"Geospatial capability '{capability_id}' was not found."
        )

    async def _fetch_provider_payload(
        self, provider_id: str, request: ProviderRequest
    ) -> dict[str, Any]:
        self.provider_registry.build_from_manifests()
        try:
            response = await self.provider_registry.fetch(provider_id, request)
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

    def _parse_bbox(self, value: str | None) -> tuple[float, float, float, float] | None:
        if not value:
            return None
        try:
            parts = tuple(float(part.strip()) for part in value.split(","))
        except ValueError as exc:
            raise GeospatialInvalidRequestError(
                "bbox must be four comma-separated numbers."
            ) from exc
        if len(parts) != 4:
            raise GeospatialInvalidRequestError(
                "bbox must be four comma-separated numbers."
            )
        return parts  # type: ignore[return-value]

    def _parse_time(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise GeospatialInvalidRequestError("time must be ISO-8601.") from exc

    def _parse_camera_identifier(self, camera_id: str) -> tuple[str | None, str]:
        normalized = camera_id.strip()
        for separator in ("/", ":"):
            if separator in normalized:
                provider_id, provider_camera_id = normalized.split(separator, 1)
                provider_id = provider_id.strip()
                provider_camera_id = provider_camera_id.strip()
                if provider_id == "windy":
                    provider_id = "windy_webcams"
                if provider_id and provider_camera_id:
                    return provider_id, provider_camera_id
        return None, normalized

    def _provider_requires_credentials(self, provider_id: str) -> bool:
        payload = self.manifest_loader.load_all()
        for item in payload.get("providers") or []:
            if str(item.get("id") or "") == provider_id:
                auth = item.get("auth")
                return bool(isinstance(auth, dict) and auth.get("required"))
        return provider_id in RuntimeRegistry.CREDENTIAL_ENV_BY_PROVIDER

    def _build_provider_account_setup(self, provider: dict[str, Any]) -> dict[str, Any]:
        provider_id = str(provider.get("id") or "")
        auth = provider.get("auth") if isinstance(provider.get("auth"), dict) else {}
        env_name = RuntimeRegistry.CREDENTIAL_ENV_BY_PROVIDER.get(provider_id)
        docs_url = self._extract_docs_url(provider)
        required = bool(auth.get("required")) or provider_id in RuntimeRegistry.CREDENTIAL_ENV_BY_PROVIDER
        auth_mode = str(auth.get("type") or ("api-key" if env_name else "none"))
        instructions = self._build_account_setup_instructions(
            provider_id=provider_id,
            docs_url=docs_url,
            env_name=env_name,
            required=required,
        )
        return {
            "provider_id": provider_id,
            "name": str(provider.get("name") or provider_id),
            "requires_credentials": required,
            "auth_mode": auth_mode,
            "docs_url": docs_url,
            "environment_variable": env_name,
            "configured": bool(env_name and os.getenv(env_name, "").strip()),
            "instructions": instructions,
        }

    @staticmethod
    def _extract_docs_url(provider: dict[str, Any]) -> str | None:
        docs = provider.get("sourceOfficialDocs")
        if isinstance(docs, list):
            for item in docs:
                if isinstance(item, str) and item.strip():
                    return item.strip()
        docs_url = provider.get("official_docs_url") or provider.get("source")
        return docs_url.strip() if isinstance(docs_url, str) and docs_url.strip() else None

    @staticmethod
    def _build_account_setup_instructions(
        *,
        provider_id: str,
        docs_url: str | None,
        env_name: str | None,
        required: bool,
    ) -> list[str]:
        if not required:
            return ["No account setup is required for public access."]
        instructions = []
        if docs_url:
            instructions.append(f"Create or sign in to a provider account using {docs_url}.")
        else:
            instructions.append("Create or sign in to the provider account.")
        instructions.append("Generate an API key or access token with map/data read permissions.")
        if env_name:
            instructions.append(f"Set the key in the {env_name} environment variable.")
        else:
            instructions.append(f"Store the key using the access configuration for {provider_id}.")
        instructions.append("Restart or refresh AEGIS so the runtime can detect the credential.")
        return instructions

    async def _fetch_binary_url(self, url: str) -> bytes:
        return await asyncio.to_thread(self._fetch_binary_url_sync, url)

    def _fetch_binary_url_sync(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "AEGIS/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()
