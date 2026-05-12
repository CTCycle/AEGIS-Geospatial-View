from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from time import monotonic
from typing import Any

from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderCircuitOpenError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


class ProviderRegistryError(Exception):
    """Base provider registry error."""


class ProviderNotRegisteredError(ProviderRegistryError):
    """Raised when no provider is registered for a provider id."""


@dataclass(frozen=True)
class ProviderExecutionPolicy:
    timeout_seconds: float = 10.0
    max_attempts: int = 1
    circuit_breaker_failures: int = 3


@dataclass(frozen=True)
class ManifestBackedProvider:
    provider_id: str
    manifest: dict[str, Any]

    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "status": "not-implemented",
                "provider": self.provider_id,
                "capability_id": request.capability_id,
            },
            attribution=self._attribution(),
            warnings=[
                "Provider framework is registered, but no concrete fetcher is bound."
            ],
        )

    def _attribution(self) -> list[str]:
        license_payload = self.manifest.get("license")
        if isinstance(license_payload, dict):
            name = str(license_payload.get("name") or "").strip()
            if name:
                return [name]
        return []


class ProviderRegistry:
    def __init__(
        self,
        *,
        manifest_loader: GeospatialManifestLoader | None = None,
        providers: list[GeospatialProvider] | None = None,
        execution_policy: ProviderExecutionPolicy | None = None,
    ) -> None:
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()
        self.execution_policy = execution_policy or ProviderExecutionPolicy()
        self._providers: dict[str, GeospatialProvider] = {}
        self._failures: dict[str, int] = {}
        self._last_call_at: dict[str, float] = {}
        self._min_call_interval_s: dict[str, float] = {}
        for provider in providers or []:
            self.register(provider)

    def register(self, provider: GeospatialProvider) -> None:
        provider_id = str(provider.provider_id).strip().lower()
        if not provider_id:
            raise ValueError("Provider id is required.")
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> GeospatialProvider:
        normalized = str(provider_id).strip().lower()
        if not normalized:
            raise ProviderNotRegisteredError("Provider id is required.")
        provider = self._providers.get(normalized)
        if provider is None:
            raise ProviderNotRegisteredError(
                f"Provider '{normalized}' is not registered."
            )
        return provider

    def list_provider_ids(self) -> list[str]:
        return sorted(self._providers)

    def configure_rate_limit(
        self, provider_id: str, *, min_call_interval_s: float
    ) -> None:
        normalized = self._normalize_provider_id(provider_id)
        self._min_call_interval_s[normalized] = max(0.0, float(min_call_interval_s))

    def build_from_manifests(self) -> None:
        payload = self.manifest_loader.load_all()
        items = []
        for collection_name in ("providers", "basemaps", "overlays", "cameras", "transit", "tools"):
            items.extend(payload.get(collection_name) or [])
        for item in items:
            provider_id = str(item.get("id") or item.get("provider") or "").strip()
            if str(item.get("capabilityKind") or "") != "metadata-only":
                provider_id = str(item.get("provider") or "").strip()
            if not provider_id:
                continue
            if provider_id.lower() in self._providers:
                continue
            self.register(self._provider_for_manifest(provider_id.lower(), dict(item)))

    async def fetch(
        self, provider_id: str, request: ProviderRequest
    ) -> ProviderResponse:
        normalized = self._normalize_provider_id(provider_id)
        provider = self.get(normalized)
        self._ensure_circuit_closed(normalized)
        await self._wait_for_rate_limit(normalized)
        attempts = max(1, int(self.execution_policy.max_attempts))
        last_error: ProviderError | None = None
        for attempt in range(attempts):
            try:
                response = await asyncio.wait_for(
                    provider.fetch(request),
                    timeout=max(0.01, float(self.execution_policy.timeout_seconds)),
                )
            except ProviderAuthError:
                raise
            except TimeoutError as exc:
                last_error = ProviderTimeoutError(
                    f"Provider '{normalized}' timed out."
                )
                self._record_failure(normalized)
                if attempt + 1 >= attempts:
                    raise last_error from exc
            except ProviderUnavailableError as exc:
                last_error = exc
                self._record_failure(normalized)
                if attempt + 1 >= attempts:
                    raise
            except ProviderError:
                self._record_failure(normalized)
                raise
            else:
                self._failures[normalized] = 0
                return response
        if last_error is not None:
            raise last_error
        raise ProviderUnavailableError(f"Provider '{normalized}' did not return data.")

    def _provider_for_manifest(
        self, provider_id: str, manifest: dict[str, Any]
    ) -> GeospatialProvider:
        if provider_id == "arcgis":
            from server.services.geospatial.providers.arcgis_rest import (
                ArcGISRestProvider,
            )

            return ArcGISRestProvider()
        if provider_id == "census":
            from server.services.geospatial.providers.census import CensusProvider

            return CensusProvider()
        if provider_id == "gibs":
            from server.services.geospatial.providers.nasa_gibs import (
                NASAGIBSProvider,
            )

            return NASAGIBSProvider()
        if provider_id == "rainviewer":
            from server.services.geospatial.providers.rainviewer import (
                RainViewerProvider,
            )

            return RainViewerProvider()
        if provider_id == "openmeteo":
            from server.services.geospatial.providers.openmeteo import (
                OpenMeteoProvider,
            )

            return OpenMeteoProvider()
        if provider_id == "overpass":
            from server.services.geospatial.providers.overpass import OverpassProvider

            return OverpassProvider()
        if provider_id == "openaq":
            from server.services.geospatial.providers.openaq import OpenAQProvider

            return OpenAQProvider(api_key=os.getenv("OPENAQ_API_KEY"))
        if provider_id == "pvgis":
            from server.services.geospatial.providers.pvgis import PVGISProvider

            return PVGISProvider()
        if provider_id == "tomtom":
            from server.services.geospatial.providers.tomtom import TomTomProvider

            return TomTomProvider(api_key=os.getenv("TOMTOM_API_KEY"))
        if provider_id == "geoapify":
            from server.services.geospatial.providers.geoapify import GeoapifyProvider

            return GeoapifyProvider(api_key=os.getenv("GEOAPIFY_API_KEY"))
        if provider_id == "windy_webcams":
            from server.services.geospatial.providers.windy_webcams import (
                WindyWebcamsProvider,
            )

            return WindyWebcamsProvider(api_key=os.getenv("WINDY_WEBCAMS_API_KEY"))
        if provider_id == "usgs":
            from server.services.geospatial.providers.usgs import USGSProvider

            return USGSProvider()
        if provider_id == "noaa":
            from server.services.geospatial.providers.noaa import NOAAProvider

            return NOAAProvider()
        if provider_id == "fema":
            from server.services.geospatial.providers.fema import FEMAProvider

            return FEMAProvider()
        if provider_id == "nasa_firms":
            from server.services.geospatial.providers.nasa_firms import (
                NASAFIRMSProvider,
            )

            return NASAFIRMSProvider(api_key=os.getenv("NASA_API_KEY"))
        if provider_id == "opentripmap":
            from server.services.geospatial.providers.opentripmap import (
                OpenTripMapProvider,
            )

            return OpenTripMapProvider(api_key=os.getenv("OPENTRIPMAP_API_KEY"))
        if provider_id == "openchargemap":
            from server.services.geospatial.providers.openchargemap import (
                OpenChargeMapProvider,
            )

            return OpenChargeMapProvider(api_key=os.getenv("OPENCHARGEMAP_API_KEY"))
        if provider_id == "nrel":
            from server.services.geospatial.providers.nrel import NRELProvider

            return NRELProvider(api_key=os.getenv("NREL_API_KEY"))
        if provider_id == "ourairports":
            from server.services.geospatial.providers.ourairports import (
                OurAirportsProvider,
            )

            return OurAirportsProvider()
        if provider_id == "gtfs_static":
            from server.services.geospatial.providers.gtfs_static import (
                GTFSStaticProvider,
            )

            return GTFSStaticProvider()
        if provider_id == "gtfs_realtime":
            from server.services.geospatial.providers.gtfs_realtime import (
                GTFSRealtimeProvider,
            )

            return GTFSRealtimeProvider()
        if provider_id == "natural_earth":
            from server.services.geospatial.providers.natural_earth import (
                NaturalEarthProvider,
            )

            return NaturalEarthProvider()
        if provider_id == "overture":
            from server.services.geospatial.providers.overture import OvertureProvider

            return OvertureProvider()
        if provider_id == "openaddresses":
            from server.services.geospatial.providers.openaddresses import (
                OpenAddressesProvider,
            )

            return OpenAddressesProvider()
        if provider_id == "local_open_data":
            from server.services.geospatial.providers.local_open_data import (
                LocalOpenDataProvider,
            )

            return LocalOpenDataProvider()
        if provider_id == "transitland":
            from server.services.geospatial.providers.transitland import (
                TransitlandProvider,
            )

            return TransitlandProvider(api_key=os.getenv("TRANSITLAND_API_KEY"))
        if provider_id == "fallback":
            from server.services.geospatial.providers.fallback import FallbackTileProvider

            return FallbackTileProvider()
        if provider_id == "osm":
            from server.services.geospatial.providers.osm import OSMProvider

            return OSMProvider()
        if provider_id == "mapillary":
            from server.services.geospatial.providers.mapillary import MapillaryProvider

            return MapillaryProvider(access_token=os.getenv("MAPILLARY_ACCESS_TOKEN"))
        return ManifestBackedProvider(provider_id=provider_id, manifest=manifest)

    def _normalize_provider_id(self, provider_id: str) -> str:
        normalized = str(provider_id).strip().lower()
        if not normalized:
            raise ProviderNotRegisteredError("Provider id is required.")
        return normalized

    def _ensure_circuit_closed(self, provider_id: str) -> None:
        limit = max(1, int(self.execution_policy.circuit_breaker_failures))
        if self._failures.get(provider_id, 0) >= limit:
            raise ProviderCircuitOpenError(
                f"Provider '{provider_id}' circuit is open after repeated failures."
            )

    def _record_failure(self, provider_id: str) -> None:
        self._failures[provider_id] = self._failures.get(provider_id, 0) + 1

    async def _wait_for_rate_limit(self, provider_id: str) -> None:
        min_interval = self._min_call_interval_s.get(provider_id, 0.0)
        if min_interval <= 0:
            self._last_call_at[provider_id] = monotonic()
            return
        now = monotonic()
        delay = min_interval - (now - self._last_call_at.get(provider_id, 0.0))
        if delay > 0:
            await asyncio.sleep(delay)
        self._last_call_at[provider_id] = monotonic()
