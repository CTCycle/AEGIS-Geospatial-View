from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from urllib.parse import quote

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
from server.services.geospatial.providers.http import fetch_bytes_url
from server.services.geospatial.providers.tomtom import build_tomtom_tile_url
from server.services.geospatial.runtime_registry import RuntimeRegistry

CAMERA_PROVIDER_ALIASES = {
    "windy": "windy_webcams",
}

###############################################################################
class GeospatialApiServiceError(Exception):
    """Base exception for geospatial API service failures."""

###############################################################################
class GeospatialCapabilityNotFoundError(GeospatialApiServiceError):
    """Raised when a requested manifest capability does not exist."""

###############################################################################
class GeospatialInvalidRequestError(GeospatialApiServiceError):
    """Raised when query parameters cannot be parsed safely."""

###############################################################################
class GeospatialTileCredentialError(GeospatialApiServiceError):
    """Raised when a tile provider credential is missing or rejected."""

###############################################################################
class GeospatialTileRequestError(GeospatialApiServiceError):
    """Raised when a tile provider request fails."""

###############################################################################
class GeospatialUnsupportedTileError(GeospatialApiServiceError):
    """Raised when a tile kind is not supported."""


###############################################################################
def normalize_geojson_feature_collection(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("type") == "FeatureCollection":
        features = value.get("features")
        return {
            "type": "FeatureCollection",
            "features": features if isinstance(features, list) else [],
        }
    if isinstance(value, dict) and value.get("type") == "Feature":
        return {
            "type": "FeatureCollection",
            "features": [value],
        }
    if isinstance(value, dict) and isinstance(value.get("features"), list):
        return {
            "type": "FeatureCollection",
            "features": value["features"],
        }
    return {"type": "FeatureCollection", "features": []}

###############################################################################
class GeospatialApiService:

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    def list_capabilities(self) -> dict[str, list[dict[str, Any]]]:
        return self.catalog_service.list_catalog()

    # -------------------------------------------------------------------------
    def list_layers(self) -> dict[str, list[dict[str, Any]]]:
        catalog = self.catalog_service.list_catalog()
        return {
            "basemaps": catalog["basemaps"],
            "overlays": catalog["overlays"],
            "cameras": catalog.get("cameras", []),
            "transit": catalog.get("transit", []),
        }

    # -------------------------------------------------------------------------
    def get_layer_health(self, layer_id: str) -> dict[str, Any]:
        manifest = self._manifest_by_id(layer_id)
        reliability = manifest.get("reliability")
        return {
            "id": layer_id,
            "provider": manifest.get("provider"),
            "reliability": reliability if isinstance(reliability, dict) else {},
            "runtime": self.runtime_registry.provider_health(layer_id),
        }

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    async def get_layer_geojson(
        self,
        layer_id: str,
        *,
        bbox: str | None,
        zoom: int | None,
        time: str | None,
        live: bool,
        incidents: bool,
    ) -> dict[str, Any]:
        payload = await self.get_layer_features(
            layer_id,
            bbox=bbox,
            zoom=zoom,
            time=time,
            live=live,
            incidents=incidents,
        )
        if payload.get("status") != "ok":
            return {"type": "FeatureCollection", "features": []}
        return normalize_geojson_feature_collection(payload.get("payload"))

    # -------------------------------------------------------------------------
    async def fetch_tomtom_tile(self, kind: str, z: int, x: int, y: int) -> bytes:
        if kind not in {"basic", "traffic-flow"}:
            raise GeospatialUnsupportedTileError("Unsupported TomTom tile type.")
        api_key = os.getenv("TOMTOM_API_KEY", "").strip()
        if not api_key:
            raise GeospatialTileCredentialError("TomTom API key is required.")
        url = build_tomtom_tile_url(kind, z, x, y, api_key)
        try:
            return await self._fetch_binary_url(url)
        except ProviderAuthError as exc:
            raise GeospatialTileCredentialError(
                "TomTom rejected the configured API key."
            ) from exc
        except (ProviderTimeoutError, ProviderUnavailableError) as exc:
            raise GeospatialTileRequestError("TomTom tile request failed.") from exc

    # -------------------------------------------------------------------------
    async def fetch_capability_tile(
        self,
        capability_id: str,
        z: int,
        x: int,
        y: int,
    ) -> bytes:
        manifest = self._manifest_by_id(capability_id)
        metadata = manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else {}
        template = str(
            metadata.get("tile_url_template")
            or metadata.get("url_template")
            or metadata.get("tile_url")
            or metadata.get("url")
            or ""
        ).strip()
        if not template:
            raise GeospatialUnsupportedTileError("Tile URL is missing from provider metadata.")
        provider = str(manifest.get("provider") or "").strip().lower()
        upstream_url = self._resolve_credentialed_tile_template(
            template=template,
            provider=provider,
            capability_id=capability_id,
            z=z,
            x=x,
            y=y,
        )
        try:
            return await self._fetch_binary_url(upstream_url)
        except ProviderAuthError as exc:
            raise GeospatialTileCredentialError(
                f"{self._humanize_provider(provider)} rejected the configured credentials."
            ) from exc
        except (ProviderTimeoutError, ProviderUnavailableError) as exc:
            raise GeospatialTileRequestError(
                f"{self._humanize_provider(provider)} tile request failed."
            ) from exc

    # -------------------------------------------------------------------------
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
            params={
                "live": True,
                **({"camera_type": camera_type} if camera_type else {}),
            },
        )
        return await self._fetch_provider_payload(provider_id, request)

    # -------------------------------------------------------------------------
    async def list_cameras_geojson(
        self,
        *,
        bbox: str | None,
        provider: str | None,
        camera_type: str | None,
    ) -> dict[str, Any]:
        payload = await self.list_cameras(
            bbox=bbox,
            provider=provider,
            camera_type=camera_type,
        )
        if payload.get("status") != "ok":
            return {"type": "FeatureCollection", "features": []}
        return normalize_geojson_feature_collection(payload.get("payload"))

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    def get_credential_status(self, provider_id: str) -> dict[str, Any]:
        env_name = RuntimeRegistry.CREDENTIAL_ENV_BY_PROVIDER.get(provider_id)
        configured = bool(env_name and os.getenv(env_name, "").strip())
        return {
            "provider": provider_id,
            "required": self._provider_requires_credentials(provider_id),
            "configured": configured,
            "environmentVariable": env_name,
        }

    # -------------------------------------------------------------------------
    def list_provider_account_setup(self) -> dict[str, list[dict[str, Any]]]:
        records = [
            record
            for payload in self._iter_manifest_payloads_for_account_setup()
            if (record := self._extract_account_setup_record(payload)) is not None
        ]
        providers = self._dedupe_account_setup_records(records)
        providers.sort(
            key=lambda item: str(item.get("name") or item.get("provider_id"))
        )
        return {"providers": providers}

    # -------------------------------------------------------------------------
    def get_provider_account_setup(self, provider_id: str) -> dict[str, Any]:
        normalized = provider_id.strip()
        for record in self.list_provider_account_setup()["providers"]:
            if str(record.get("provider_id") or "") == normalized:
                return record
        raise GeospatialCapabilityNotFoundError(
            f"Geospatial provider '{provider_id}' was not found."
        )

    # -------------------------------------------------------------------------
    def audit_sources(self) -> LayerAuditReport:
        return audit_all_manifests(strict=True)

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    def _parse_bbox(
        self, value: str | None
    ) -> tuple[float, float, float, float] | None:
        if not value:
            return None
        try:
            parts = [float(part.strip()) for part in value.split(",")]
        except ValueError as exc:
            raise GeospatialInvalidRequestError(
                "bbox must be four comma-separated numbers."
            ) from exc
        if len(parts) != 4:
            raise GeospatialInvalidRequestError(
                "bbox must be four comma-separated numbers."
            )
        min_lon, min_lat, max_lon, max_lat = parts
        return min_lon, min_lat, max_lon, max_lat

    # -------------------------------------------------------------------------
    def _parse_time(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise GeospatialInvalidRequestError("time must be ISO-8601.") from exc

    # -------------------------------------------------------------------------
    def _parse_camera_identifier(self, camera_id: str) -> tuple[str | None, str]:
        normalized = camera_id.strip()
        for separator in ("/", ":"):
            if separator in normalized:
                provider_id, provider_camera_id = normalized.split(separator, 1)
                provider_id = provider_id.strip()
                provider_camera_id = provider_camera_id.strip()
                if provider_id and provider_camera_id:
                    canonical_provider_id = CAMERA_PROVIDER_ALIASES.get(
                        provider_id, provider_id
                    )
                    return canonical_provider_id, provider_camera_id
        return None, normalized

    # -------------------------------------------------------------------------
    def _provider_requires_credentials(self, provider_id: str) -> bool:
        for item in self._iter_manifest_payloads_for_account_setup():
            auth = item.get("auth") if isinstance(item.get("auth"), dict) else {}
            manifest_provider = str(item.get("provider") or item.get("id") or "")
            access_id = str(auth.get("accessPageProviderId") or "")
            provider_key = str(auth.get("providerKey") or "")
            if provider_id in {manifest_provider, access_id, provider_key}:
                return bool(auth.get("required"))
        return provider_id in RuntimeRegistry.CREDENTIAL_ENV_BY_PROVIDER

    # -------------------------------------------------------------------------
    def _iter_manifest_payloads_for_account_setup(self) -> Iterator[dict[str, Any]]:
        payload = self.manifest_loader.load_all()
        for collection_name in ("providers", "overlays", "transit", "cameras"):
            for item in payload.get(collection_name) or []:
                if isinstance(item, dict):
                    yield item

    # -------------------------------------------------------------------------
    def _extract_account_setup_record(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        auth = payload.get("auth") if isinstance(payload.get("auth"), dict) else {}
        requires_credentials = bool(auth.get("required"))
        provider_key = str(
            auth.get("providerKey")
            or payload.get("provider")
            or payload.get("id")
            or ""
        ).strip()
        access_provider_id = str(
            auth.get("accessPageProviderId") or provider_key
        ).strip()
        account_setup = (
            payload.get("account_setup")
            if isinstance(payload.get("account_setup"), dict)
            else {}
        )
        has_account_setup = isinstance(account_setup.get("automation"), dict)
        if (
            (not requires_credentials and not has_account_setup)
            or not provider_key
            or not access_provider_id
        ):
            return None
        if provider_key in {"census", "openaip", "sentinel_hub"}:
            return None

        env_name = RuntimeRegistry.CREDENTIAL_ENV_BY_PROVIDER.get(provider_key)
        docs_url = self._extract_docs_url(payload)
        automation = self._build_account_setup_automation(
            provider_key=provider_key,
            docs_url=docs_url,
            account_setup=account_setup,
        )
        instructions = self._build_account_setup_instructions(
            provider_id=provider_key,
            docs_url=docs_url,
            env_name=env_name,
            required=True,
        )
        metadata = (
            payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        )
        return {
            "provider_id": provider_key,
            "name": str(metadata.get("label") or payload.get("name") or provider_key),
            "requires_credentials": True,
            "auth_mode": str(auth.get("type") or "api-key"),
            "docs_url": docs_url,
            "environment_variable": env_name,
            "configured": bool(env_name and os.getenv(env_name, "").strip()),
            "instructions": instructions,
            "automation": automation,
            "credential_storage_key": provider_key,
            "credential_label": "api_key",
            "key_format_hint": self._key_format_hint(provider_key),
            "validation_supported": provider_key
            in {"tomtom", "windy_webcams", "openaq", "nrel", "nasa_firms"},
        }

    # -------------------------------------------------------------------------
    def _dedupe_account_setup_records(
        self, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for record in records:
            key = str(record.get("provider_id") or "")
            if not key:
                continue
            current = deduped.get(key)
            if current is None or self._account_setup_specificity(
                record
            ) > self._account_setup_specificity(current):
                deduped[key] = record
        return list(deduped.values())

    # -------------------------------------------------------------------------
    @staticmethod
    def _account_setup_specificity(record: dict[str, Any]) -> int:
        automation = (
            record.get("automation")
            if isinstance(record.get("automation"), dict)
            else {}
        )
        return (
            sum(
                1
                for field in ("signup_url", "developer_portal_url", "docs_url")
                if automation.get(field)
            )
            + len(automation.get("user_action_notes") or [])
            + len(automation.get("safety_notes") or [])
        )

    # -------------------------------------------------------------------------
    def _build_account_setup_automation(
        self,
        *,
        provider_key: str,
        docs_url: str | None,
        account_setup: dict[str, Any],
    ) -> dict[str, Any]:
        raw = (
            account_setup.get("automation")
            if isinstance(account_setup.get("automation"), dict)
            else {}
        )
        support = str(
            raw.get("support") or self._default_automation_support(provider_key)
        )
        signup_url = raw.get("signup_url") or account_setup.get("account_url")
        portal_url = (
            raw.get("developer_portal_url")
            or account_setup.get("dashboard_url")
            or signup_url
        )
        automation_docs_url = (
            raw.get("docs_url") or account_setup.get("documentation_url") or docs_url
        )
        return {
            "support": support,
            "signup_url": signup_url if isinstance(signup_url, str) else None,
            "developer_portal_url": portal_url if isinstance(portal_url, str) else None,
            "docs_url": automation_docs_url
            if isinstance(automation_docs_url, str)
            else None,
            "required_fields": [
                field
                for field in raw.get("required_fields", [])
                if isinstance(field, dict) and not field.get("sensitive")
            ],
            "user_action_notes": self._string_list(raw.get("user_action_notes"))
            or self._default_user_action_notes(provider_key, support),
            "safety_notes": self._string_list(raw.get("safety_notes"))
            or self._default_safety_notes(provider_key, support),
            "experimental": bool(raw.get("experimental", True)),
            "experimental_label": str(
                raw.get("experimental_label") or "Experimental guided setup"
            ),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _default_automation_support(provider_key: str) -> str:
        if provider_key == "opentripmap":
            return "unsupported"
        if provider_key == "google_maps":
            return "manual_only"
        return "agent_assisted"

    # -------------------------------------------------------------------------
    @staticmethod
    def _default_user_action_notes(provider_key: str, support: str) -> list[str]:
        if support == "unsupported":
            return [
                "Open the official documentation and complete provider setup manually."
            ]
        notes = [
            "Open the provider portal from AEGIS and complete account-controlled steps in the provider site.",
            "Pause for any CAPTCHA, login, email verification, 2FA, billing, consent, or key-generation prompts.",
            "Paste the generated API key back into AEGIS when the provider flow is complete.",
        ]
        if provider_key == "google_maps":
            notes.insert(
                1,
                "Create or select a Google Cloud project, enable required APIs, configure billing, and restrict the key in Google Cloud.",
            )
        return notes

    # -------------------------------------------------------------------------
    @staticmethod
    def _default_safety_notes(provider_key: str, support: str) -> list[str]:
        notes = [
            "AEGIS does not collect provider passwords, CAPTCHA responses, 2FA codes, recovery codes, or billing credentials.",
            "Guided setup is experimental and best-effort; manual provider instructions remain the fallback.",
        ]
        if provider_key == "google_maps":
            notes.append(
                "Google Maps Platform production API-key setup requires the user to complete Google Cloud account, project, API, and billing setup manually."
            )
        if support == "unsupported":
            notes.append(
                "Automation support is not currently verified for this provider."
            )
        return notes

    # -------------------------------------------------------------------------
    @staticmethod
    def _key_format_hint(provider_key: str) -> str | None:
        return {
            "nasa_firms": "NASA FIRMS MAP_KEY value",
            "openaq": "OpenAQ API key sent with the X-API-Key header",
            "windy_webcams": "Windy Webcams API key",
        }.get(provider_key)

    # -------------------------------------------------------------------------
    @staticmethod
    def _string_list(value: Any) -> list[str]:
        return (
            [item for item in value if isinstance(item, str) and item.strip()]
            if isinstance(value, list)
            else []
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_docs_url(provider: dict[str, Any]) -> str | None:
        metadata = (
            provider.get("metadata")
            if isinstance(provider.get("metadata"), dict)
            else {}
        )
        for value in (
            metadata.get("official_docs_url"),
            provider.get("official_docs_url"),
            provider.get("source"),
        ):
            if isinstance(value, str) and value.strip():
                return value.strip()
        docs = provider.get("sourceOfficialDocs")
        if isinstance(docs, list):
            for item in docs:
                if isinstance(item, str) and item.strip():
                    return item.strip()
        return None

    # -------------------------------------------------------------------------
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
            instructions.append(
                f"Create or sign in to a provider account using {docs_url}."
            )
        else:
            instructions.append("Create or sign in to the provider account.")
        instructions.append(
            "Generate an API key or access token with map/data read permissions."
        )
        if env_name:
            instructions.append(
                f"Set the key in the {env_name} environment variable or save it through Access settings."
            )
        else:
            instructions.append(
                f"Store the key using the access configuration for {provider_id}."
            )
        instructions.append("Refresh AEGIS so the runtime can detect the credential.")
        return instructions

    # -------------------------------------------------------------------------
    def _resolve_credentialed_tile_template(
        self,
        *,
        template: str,
        provider: str,
        capability_id: str,
        z: int,
        x: int,
        y: int,
    ) -> str:
        env_name = RuntimeRegistry.CREDENTIAL_ENV_BY_PROVIDER.get(provider)
        if "{api_key}" in template:
            if not env_name:
                raise GeospatialUnsupportedTileError(
                    f"No credential mapping is configured for provider '{provider}'."
                )
            api_key = os.getenv(env_name, "").strip()
            if not api_key:
                raise GeospatialTileCredentialError(
                    f"{self._humanize_provider(provider)} credentials are required."
                )
            template = template.replace("{api_key}", quote(api_key, safe=""))
        resolved = (
            template.replace("{z}", str(z))
            .replace("{x}", str(x))
            .replace("{y}", str(y))
        )
        if resolved == template and all(token not in template for token in ("{z}", "{x}", "{y}")):
            raise GeospatialUnsupportedTileError(
                f"Capability '{capability_id}' does not expose a tile template."
            )
        return resolved

    # -------------------------------------------------------------------------
    @staticmethod
    def _humanize_provider(provider: str) -> str:
        lookup = {
            "tomtom": "TomTom",
            "geoapify": "Geoapify",
            "google_maps": "Google Maps",
            "openaq": "OpenAQ",
            "arcgis": "ArcGIS",
        }
        return lookup.get(provider, provider or "Provider")

    # -------------------------------------------------------------------------
    async def _fetch_binary_url(self, url: str) -> bytes:
        return await fetch_bytes_url(url, {"User-Agent": "AEGIS/1.0"})
