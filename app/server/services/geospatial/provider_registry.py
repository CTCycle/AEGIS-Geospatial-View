from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from time import monotonic
from typing import Any, cast

from server.contracts.geospatial import GeospatialProviderLayerDescriptor
from server.domain.geospatial.providers import ProviderExecutionPolicy
from server.domain.geospatial.registry import GeospatialManifestSnapshot
from server.services.geospatial.credential_resolver import GeospatialCredentialResolver
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
    safe_request_params,
)
from server.services.geospatial.providers.census import CensusProvider
from server.services.geospatial.providers.eea import EEAProvider
from server.services.geospatial.providers.esa import ESAProvider
from server.services.geospatial.providers.eurostat import EurostatProvider
from server.services.geospatial.providers.fema import FEMAProvider
from server.services.geospatial.providers.gtfs_realtime import GTFSRealtimeProvider
from server.services.geospatial.providers.gtfs_static import GTFSStaticProvider
from server.services.geospatial.providers.local_open_data import LocalOpenDataProvider
from server.services.geospatial.providers.mapillary import MapillaryProvider
from server.services.geospatial.providers.nasa_firms import NASAFIRMSProvider
from server.services.geospatial.providers.nasa_gibs import NASAGIBSProvider
from server.services.geospatial.providers.natural_earth import NaturalEarthProvider
from server.services.geospatial.providers.noaa import NOAAProvider
from server.services.geospatial.providers.nominatim import NominatimProvider
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
from server.services.geospatial.providers.soilgrids import SoilGridsProvider
from server.services.geospatial.providers.tomtom import TomTomProvider
from server.services.geospatial.providers.mobility_database import (
    MobilityDatabaseProvider,
)
from server.services.geospatial.providers.usgs import USGSProvider
from server.services.geospatial.providers.windy_webcams import WindyWebcamsProvider

ProviderFactory = Callable[[str | None], Any]


PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "arcgis": lambda _credential: ArcGISRestProvider(),
    "census": lambda _credential: CensusProvider(),
    "gibs": lambda _credential: NASAGIBSProvider(),
    "eea": lambda _credential: EEAProvider(),
    "esa": lambda _credential: ESAProvider(),
    "eurostat": lambda _credential: EurostatProvider(),
    "rainviewer": lambda _credential: RainViewerProvider(),
    "openmeteo": lambda _credential: OpenMeteoProvider(),
    "overpass": lambda _credential: OverpassProvider(),
    "openaq": lambda credential: OpenAQProvider(api_key=credential),
    "pvgis": lambda _credential: PVGISProvider(),
    "tomtom": lambda credential: TomTomProvider(api_key=credential),
    "windy_webcams": lambda credential: WindyWebcamsProvider(api_key=credential),
    "usgs": lambda _credential: USGSProvider(),
    "noaa": lambda _credential: NOAAProvider(),
    "fema": lambda _credential: FEMAProvider(),
    "nasa_firms": lambda credential: NASAFIRMSProvider(api_key=credential),
    "soilgrids": lambda _credential: SoilGridsProvider(),
    "opentripmap": lambda credential: OpenTripMapProvider(api_key=credential),
    "openchargemap": lambda credential: OpenChargeMapProvider(api_key=credential),
    "ourairports": lambda _credential: OurAirportsProvider(),
    "gtfs_static": lambda _credential: GTFSStaticProvider(),
    "gtfs_realtime": lambda _credential: GTFSRealtimeProvider(),
    "natural_earth": lambda _credential: NaturalEarthProvider(),
    "overture": lambda _credential: OvertureProvider(),
    "openaddresses": lambda _credential: OpenAddressesProvider(),
    "local_open_data": lambda _credential: LocalOpenDataProvider(),
    "mobility_database": lambda _credential: MobilityDatabaseProvider(),
    "nominatim": lambda _credential: NominatimProvider(),
    "mapillary": lambda credential: MapillaryProvider(access_token=credential),
}

LOGGER = logging.getLogger(__name__)


###############################################################################
class ProviderRegistryError(Exception):
    """Base provider registry error."""


###############################################################################
class ProviderNotRegisteredError(ProviderRegistryError):
    """Raised when no provider is registered for a provider id."""


###############################################################################
class ProviderRegistry:
    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        catalog_snapshot: GeospatialManifestSnapshot | None = None,
        manifest_loader: GeospatialManifestLoader | None = None,
        providers: list[GeospatialProvider] | None = None,
        execution_policy: ProviderExecutionPolicy | None = None,
        credential_resolver: GeospatialCredentialResolver | None = None,
    ) -> None:
        loader = manifest_loader or GeospatialManifestLoader()
        self.catalog_snapshot = (
            catalog_snapshot
            or GeospatialManifestSnapshot.from_payload(loader.load_all())
        )
        self.execution_policy = execution_policy or ProviderExecutionPolicy()
        self.credential_resolver = credential_resolver or GeospatialCredentialResolver()
        self._providers: dict[str, GeospatialProvider] = {}
        self._failures: dict[str, int] = {}
        self._circuit_opened_at: dict[str, float] = {}
        self._last_call_at: dict[str, float] = {}
        self._min_call_interval_s: dict[str, float] = {}
        for provider in providers or []:
            self.register(provider)
        self._manifest_providers_built = False
        if providers is None and (
            catalog_snapshot is not None or manifest_loader is None
        ):
            self._build_from_catalog_snapshot()

    # -------------------------------------------------------------------------
    def register(self, provider: GeospatialProvider) -> None:
        provider_id = str(provider.provider_id).strip().lower()
        if not provider_id:
            raise ValueError("Provider id is required.")
        self._providers[provider_id] = provider

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    def list_provider_ids(self) -> list[str]:
        return sorted(self._providers)

    # -------------------------------------------------------------------------
    def configure_rate_limit(
        self, provider_id: str, *, min_call_interval_s: float
    ) -> None:
        normalized = self._normalize_provider_id(provider_id)
        self._min_call_interval_s[normalized] = max(0.0, float(min_call_interval_s))

    # -------------------------------------------------------------------------
    def build_from_manifests(self) -> None:
        if self._manifest_providers_built:
            return
        self._build_from_catalog_snapshot()

    # -------------------------------------------------------------------------
    def _build_from_catalog_snapshot(self) -> None:
        items: list[tuple[str, dict[str, Any]]] = []
        for collection_name in (
            "providers",
            "basemaps",
            "overlays",
            "cameras",
            "transit",
            "tools",
        ):
            for item in getattr(self.catalog_snapshot, collection_name):
                items.append((collection_name, dict(item)))
        for collection_name, item in items:
            capability_kind = str(item.get("capabilityKind") or "").strip().lower()
            if collection_name != "providers" and capability_kind in {
                "basemap",
                "metadata",
                "metadata-only",
            }:
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
        self._manifest_providers_built = True

    # -------------------------------------------------------------------------
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
            started = monotonic()
            LOGGER.info(
                "provider_request provider=%s capability=%s attempt=%s bbox=%s zoom=%s time=%s params=%s",
                normalized,
                request.capability_id,
                attempt + 1,
                request.bbox,
                request.zoom,
                request.time.isoformat() if request.time else None,
                safe_request_params(request.params),
            )
            try:
                response = await asyncio.wait_for(
                    self._fetch_provider(provider, request),
                    timeout=max(0.01, float(self.execution_policy.timeout_seconds)),
                )
            except ProviderAuthError:
                raise
            except TimeoutError as exc:
                last_error = ProviderTimeoutError(f"Provider '{normalized}' timed out.")
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
                self._circuit_opened_at.pop(normalized, None)
                LOGGER.info(
                    "provider_response provider=%s capability=%s attempt=%s status=%s type=%s stale=%s partial=%s elapsed_ms=%s",
                    normalized,
                    request.capability_id,
                    attempt + 1,
                    response.result_status,
                    response.result_type,
                    response.stale,
                    response.partial,
                    int((monotonic() - started) * 1000),
                )
                return response_without_credentials(response)
        if last_error is not None:
            raise last_error
        raise ProviderUnavailableError(f"Provider '{normalized}' did not return data.")

    # -------------------------------------------------------------------------
    async def list_layers(
        self,
        provider_id: str,
        *,
        query: str | None = None,
        limit: int = 100,
        refresh: bool = False,
    ) -> list[GeospatialProviderLayerDescriptor]:
        normalized = self._normalize_provider_id(provider_id)
        provider = self.get(normalized)
        list_layers = cast(Callable[..., Any], getattr(provider, "list_layers", None))
        if not callable(list_layers):
            raise ProviderUnavailableError(
                f"Provider '{normalized}' does not support live layer discovery."
            )
        self._ensure_circuit_closed(normalized)
        await self._wait_for_rate_limit(normalized)
        try:
            return await asyncio.wait_for(
                list_layers(query=query, limit=limit, refresh=refresh),
                timeout=max(0.01, float(self.execution_policy.timeout_seconds)),
            )
        except TimeoutError as exc:
            self._record_failure(normalized)
            raise ProviderTimeoutError(f"Provider '{normalized}' timed out.") from exc

    # -------------------------------------------------------------------------
    async def describe_layer(
        self,
        provider_id: str,
        layer_id: str,
        *,
        refresh: bool = False,
    ) -> GeospatialProviderLayerDescriptor:
        normalized = self._normalize_provider_id(provider_id)
        provider = self.get(normalized)
        describe_layer = cast(
            Callable[..., Any], getattr(provider, "describe_layer", None)
        )
        if not callable(describe_layer):
            raise ProviderUnavailableError(
                f"Provider '{normalized}' does not support live layer discovery."
            )
        self._ensure_circuit_closed(normalized)
        await self._wait_for_rate_limit(normalized)
        try:
            return await asyncio.wait_for(
                describe_layer(layer_id, refresh=refresh),
                timeout=max(0.01, float(self.execution_policy.timeout_seconds)),
            )
        except TimeoutError as exc:
            self._record_failure(normalized)
            raise ProviderTimeoutError(f"Provider '{normalized}' timed out.") from exc

    # -------------------------------------------------------------------------
    async def _fetch_provider(
        self, provider: GeospatialProvider, request: ProviderRequest
    ) -> ProviderResponse:
        fetch_features = cast(
            Callable[..., Any], getattr(provider, "fetch_features", None)
        )
        if callable(fetch_features):
            response = await fetch_features(request)
            if isinstance(response, ProviderResponse):
                return response
        return await provider.fetch(request)

    # -------------------------------------------------------------------------
    def _provider_for_manifest(
        self, provider_id: str, manifest: dict[str, Any]
    ) -> GeospatialProvider:
        factory = PROVIDER_FACTORIES.get(provider_id)
        if factory is not None:
            credential = self.credential_resolver.resolve(provider_id, mark_used=True)
            return factory(credential)
        capability_id = str(manifest.get("id") or "").strip()
        raise ProviderNotRegisteredError(
            f"Provider '{provider_id}' is not registered for manifest '{capability_id}'."
        )

    # -------------------------------------------------------------------------
    def _normalize_provider_id(self, provider_id: str) -> str:
        normalized = str(provider_id).strip().lower()
        if not normalized:
            raise ProviderNotRegisteredError("Provider id is required.")
        return normalized

    # -------------------------------------------------------------------------
    def _ensure_circuit_closed(self, provider_id: str) -> None:
        limit = max(1, int(self.execution_policy.circuit_breaker_failures))
        if self._failures.get(provider_id, 0) >= limit:
            opened_at = self._circuit_opened_at.get(provider_id, monotonic())
            recovery_seconds = max(
                0.0, float(self.execution_policy.circuit_recovery_seconds)
            )
            if monotonic() - opened_at >= recovery_seconds:
                self._failures[provider_id] = 0
                self._circuit_opened_at.pop(provider_id, None)
                return
            raise ProviderCircuitOpenError(
                f"Provider '{provider_id}' circuit is open after repeated failures."
            )

    # -------------------------------------------------------------------------
    def _record_failure(self, provider_id: str) -> None:
        failures = self._failures.get(provider_id, 0) + 1
        self._failures[provider_id] = failures
        limit = max(1, int(self.execution_policy.circuit_breaker_failures))
        if failures >= limit:
            self._circuit_opened_at.setdefault(provider_id, monotonic())

    # -------------------------------------------------------------------------
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
