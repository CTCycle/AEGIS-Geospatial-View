from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from server.repositories.credential_material import (
    CredentialEncryptionMaterialRepository,
)
from server.repositories.credentials import CredentialRepository
from server.repositories.database.sqlite import SQLiteRepository
from server.domain.geospatial.providers import ProviderExecutionPolicy
from server.domain.geospatial.registry import GeospatialManifestSnapshot
from server.services.geospatial.api_service import GeospatialApiService
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.catalog import GeospatialCatalogService
from server.services.geospatial.credential_resolver import GeospatialCredentialResolver
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.nominatim import NominatimService
from server.services.geospatial.openmeteo import OpenMeteoService
from server.services.geospatial.overpass import OverpassService
from server.services.geospatial.provider_registry import (
    PROVIDER_FACTORIES,
    ProviderRegistry,
)
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.geospatial.providers.nominatim import NominatimProvider
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider
from server.services.geospatial.providers.overpass import OverpassProvider
from server.services.geospatial.providers.rainviewer import RainViewerProvider
from server.services.geospatial.rainviewer import RainViewerService
from server.services.cryptography import CredentialEncryptionService

###############################################################################
@dataclass(frozen=True)
class GeospatialRuntime:
    catalog_snapshot: GeospatialManifestSnapshot
    capability_registry: CapabilityRegistry
    runtime_registry: RuntimeRegistry
    provider_registry: ProviderRegistry
    catalog_service: GeospatialCatalogService
    api_service: GeospatialApiService
    credential_resolver: GeospatialCredentialResolver
    credentials_repo: CredentialRepository
    crypto_service: CredentialEncryptionService
    nominatim_service: NominatimService
    openmeteo_service: OpenMeteoService
    overpass_service: OverpassService
    rainviewer_service: RainViewerService

###############################################################################
def build_provider_execution_policy(
    settings: Any | None = None,
) -> ProviderExecutionPolicy:
    """Build the sole provider transport policy from application settings."""

    agent_settings = getattr(settings, "agent_execution", None)
    source_timeout_names = {
        "nominatim": "nominatim",
        "openmeteo": "openmeteo",
        "overpass": "overpass",
        "rainviewer": "rainviewer",
    }
    provider_timeouts: dict[str, float] = {}
    for provider_id, settings_name in source_timeout_names.items():
        source_settings = getattr(settings, settings_name, None)
        timeout = getattr(source_settings, "timeout", None)
        if isinstance(timeout, (int, float)) and timeout > 0:
            provider_timeouts[provider_id] = float(timeout)
    gibs_settings = getattr(settings, "gibs", None)
    gibs_timeouts = [
        getattr(gibs_settings, "timeout", None),
        getattr(gibs_settings, "layer_sync_timeout", None),
    ]
    valid_gibs_timeouts = [
        float(value)
        for value in gibs_timeouts
        if isinstance(value, (int, float)) and value > 0
    ]
    if valid_gibs_timeouts:
        provider_timeouts["gibs"] = max(valid_gibs_timeouts)

    return ProviderExecutionPolicy(
        timeout_seconds=float(
            getattr(agent_settings, "provider_request_seconds", 10.0)
        ),
        provider_timeout_seconds=provider_timeouts,
        max_attempts=int(getattr(agent_settings, "provider_max_attempts", 2)),
        retry_backoff_base_seconds=float(
            getattr(agent_settings, "retry_backoff_base_seconds", 0.25)
        ),
        retry_backoff_max_seconds=float(
            getattr(agent_settings, "retry_backoff_max_seconds", 2.0)
        ),
    )

###############################################################################
def build_geospatial_runtime(
    database: SQLiteRepository,
    *,
    settings: Any | None = None,
) -> GeospatialRuntime:
    manifest_loader = GeospatialManifestLoader()
    catalog_snapshot = GeospatialManifestSnapshot.from_payload(
        manifest_loader.load_all()
    )
    credentials_repo = CredentialRepository(database)
    crypto_service = CredentialEncryptionService(
        material_repo=CredentialEncryptionMaterialRepository(database)
    )
    credential_resolver = GeospatialCredentialResolver(
        credentials_repo=credentials_repo,
        crypto_service=crypto_service,
    )
    runtime_registry = RuntimeRegistry(
        catalog_snapshot=catalog_snapshot,
        credentials_repo=credentials_repo,
        credential_resolver=credential_resolver,
    )
    capability_registry = CapabilityRegistry.from_catalog_snapshot(catalog_snapshot)
    catalog_service = GeospatialCatalogService(
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
    )
    nominatim_service = NominatimService(settings=getattr(settings, "nominatim", None))
    openmeteo_service = OpenMeteoService(settings=getattr(settings, "openmeteo", None))
    overpass_service = OverpassService(settings=getattr(settings, "overpass", None))
    rainviewer_service = RainViewerService(
        settings=getattr(settings, "rainviewer", None)
    )
    provider_factories = dict(PROVIDER_FACTORIES)
    provider_factories.update(
        {
            "nominatim": lambda _credential: NominatimProvider(
                settings=getattr(settings, "nominatim", None)
            ),
            "openmeteo": lambda _credential: OpenMeteoProvider(
                service=openmeteo_service
            ),
            "overpass": lambda _credential: OverpassProvider(
                service=overpass_service
            ),
            "rainviewer": lambda _credential: RainViewerProvider(
                service=rainviewer_service
            ),
        }
    )
    provider_registry = ProviderRegistry(
        catalog_snapshot=catalog_snapshot,
        credential_resolver=credential_resolver,
        execution_policy=build_provider_execution_policy(settings),
        provider_factories=provider_factories,
    )
    api_service = GeospatialApiService(
        catalog_service=catalog_service,
        catalog_snapshot=catalog_snapshot,
        runtime_registry=runtime_registry,
        provider_registry=provider_registry,
        credential_resolver=credential_resolver,
    )
    return GeospatialRuntime(
        catalog_snapshot=catalog_snapshot,
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
        provider_registry=provider_registry,
        catalog_service=catalog_service,
        api_service=api_service,
        credential_resolver=credential_resolver,
        credentials_repo=credentials_repo,
        crypto_service=crypto_service,
        nominatim_service=nominatim_service,
        openmeteo_service=openmeteo_service,
        overpass_service=overpass_service,
        rainviewer_service=rainviewer_service,
    )
