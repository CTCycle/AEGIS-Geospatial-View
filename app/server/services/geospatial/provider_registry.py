from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Any

from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.providers.arcgis_rest import ArcGISRestProvider
from server.services.geospatial.providers.base import (
    GeospatialProvider,
    ProviderAuthError,
    ProviderCircuitOpenError,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    ProviderUnavailableError,
    response_without_credentials,
)
from server.services.geospatial.providers.census import CensusProvider
from server.services.geospatial.providers.eea import EEAProvider
from server.services.geospatial.providers.esa import ESAProvider
from server.services.geospatial.providers.eurostat import EurostatProvider
from server.services.geospatial.providers.fema import FEMAProvider
from server.services.geospatial.providers.geoapify import GeoapifyProvider
from server.services.geospatial.providers.gtfs_realtime import GTFSRealtimeProvider
from server.services.geospatial.providers.gtfs_static import GTFSStaticProvider
from server.services.geospatial.providers.local_open_data import LocalOpenDataProvider
from server.services.geospatial.providers.mapillary import MapillaryProvider
from server.services.geospatial.providers.nasa_firms import NASAFIRMSProvider
from server.services.geospatial.providers.nasa_gibs import NASAGIBSProvider
from server.services.geospatial.providers.natural_earth import NaturalEarthProvider
from server.services.geospatial.providers.noaa import NOAAProvider
from server.services.geospatial.providers.nominatim import NominatimProvider
from server.services.geospatial.providers.nrel import NRELProvider
from server.services.geospatial.providers.openaddresses import OpenAddressesProvider
from server.services.geospatial.providers.openaq import OpenAQProvider
from server.services.geospatial.providers.openchargemap import OpenChargeMapProvider
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider
from server.services.geospatial.providers.opentripmap import OpenTripMapProvider
from server.services.geospatial.providers.ourairports import OurAirportsProvider
from server.services.geospatial.providers.overpass import OverpassProvider
from server.services.geospatial.providers.overture import OvertureProvider
from server.services.geospatial.providers.pvgis import PVGISProvider
from server.services.geospatial.providers.rainviewer import RainViewerProvider
from server.services.geospatial.providers.tomtom import TomTomProvider
from server.services.geospatial.providers.transitland import TransitlandProvider
from server.services.geospatial.providers.usgs import USGSProvider
from server.services.geospatial.providers.windy_webcams import WindyWebcamsProvider


ProviderFactory = Callable[[], GeospatialProvider]


PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "arcgis": ArcGISRestProvider,
    "census": CensusProvider,
    "gibs": NASAGIBSProvider,
    "eea": EEAProvider,
    "esa": ESAProvider,
    "eurostat": EurostatProvider,
    "rainviewer": RainViewerProvider,
    "openmeteo": OpenMeteoProvider,
    "overpass": OverpassProvider,
    "openaq": lambda: OpenAQProvider(api_key=os.getenv("OPENAQ_API_KEY")),
    "pvgis": PVGISProvider,
    "tomtom": lambda: TomTomProvider(api_key=os.getenv("TOMTOM_API_KEY")),
    "geoapify": lambda: GeoapifyProvider(api_key=os.getenv("GEOAPIFY_API_KEY")),
    "windy_webcams": lambda: WindyWebcamsProvider(
        api_key=os.getenv("WINDY_WEBCAMS_API_KEY")
    ),
    "usgs": USGSProvider,
    "noaa": NOAAProvider,
    "fema": FEMAProvider,
    "nasa_firms": lambda: NASAFIRMSProvider(api_key=os.getenv("NASA_API_KEY")),
    "opentripmap": lambda: OpenTripMapProvider(
        api_key=os.getenv("OPENTRIPMAP_API_KEY")
    ),
    "openchargemap": lambda: OpenChargeMapProvider(
        api_key=os.getenv("OPENCHARGEMAP_API_KEY")
    ),
    "nrel": lambda: NRELProvider(api_key=os.getenv("NREL_API_KEY")),
    "ourairports": OurAirportsProvider,
    "gtfs_static": GTFSStaticProvider,
    "gtfs_realtime": GTFSRealtimeProvider,
    "natural_earth": NaturalEarthProvider,
    "overture": OvertureProvider,
    "openaddresses": OpenAddressesProvider,
    "local_open_data": LocalOpenDataProvider,
    "transitland": lambda: TransitlandProvider(
        api_key=os.getenv("TRANSITLAND_API_KEY")
    ),
    "nominatim": NominatimProvider,
    "mapillary": lambda: MapillaryProvider(
        access_token=os.getenv("MAPILLARY_ACCESS_TOKEN")
    ),
}


class ProviderRegistryError(Exception):
    """Base provider registry error."""


class ProviderNotRegisteredError(ProviderRegistryError):
    """Raised when no provider is registered for a provider id."""


from server.domain.geospatial.providers import ProviderExecutionPolicy


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
        for collection_name in (
            "providers",
            "basemaps",
            "overlays",
            "cameras",
            "transit",
            "tools",
        ):
            for item in payload.get(collection_name) or []:
                if isinstance(item, dict):
                    items.append((collection_name, item))
        for collection_name, item in items:
            capability_kind = str(item.get("capabilityKind") or "").strip().lower()
            if (
                collection_name != "providers"
                and capability_kind in {"basemap", "metadata", "metadata-only"}
            ):
                continue
            fallback_provider_id = (
                item.get("id") if collection_name == "providers" else ""
            )
            provider_id = str(item.get("provider") or fallback_provider_id).strip()
            if not provider_id:
                continue
            if provider_id.lower() in self._providers:
                continue
            if (
                collection_name == "providers"
                and provider_id.lower() not in PROVIDER_FACTORIES
            ):
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
                    self._fetch_provider(provider, request),
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
                return response_without_credentials(response)
        if last_error is not None:
            raise last_error
        raise ProviderUnavailableError(f"Provider '{normalized}' did not return data.")

    async def _fetch_provider(
        self, provider: GeospatialProvider, request: ProviderRequest
    ) -> ProviderResponse:
        fetch_features = getattr(provider, "fetch_features", None)
        if callable(fetch_features):
            response = await fetch_features(request)
            if isinstance(response, ProviderResponse):
                return response
        return await provider.fetch(request)

    def _provider_for_manifest(
        self, provider_id: str, manifest: dict[str, Any]
    ) -> GeospatialProvider:
        factory = PROVIDER_FACTORIES.get(provider_id)
        if factory is not None:
            return factory()
        capability_id = str(manifest.get("id") or "").strip()
        raise ProviderNotRegisteredError(
            f"Provider '{provider_id}' is not registered for manifest '{capability_id}'."
        )

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
