from __future__ import annotations

from dataclasses import dataclass

from server.repositories.credentials import CredentialRepository
from server.repositories.database.contracts import DatabaseBackend
from server.services.geospatial.api_service import GeospatialApiService
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.catalog import GeospatialCatalogService
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.runtime_registry import RuntimeRegistry

###############################################################################
@dataclass(frozen=True)
class GeospatialRuntime:
    api_service: GeospatialApiService

###############################################################################
def build_geospatial_runtime(database: DatabaseBackend) -> GeospatialRuntime:
    manifest_loader = GeospatialManifestLoader()
    credentials_repo = CredentialRepository(database)
    runtime_registry = RuntimeRegistry(
        manifest_loader=manifest_loader,
        credentials_repo=credentials_repo,
    )
    capability_registry = CapabilityRegistry(manifest_loader=manifest_loader)
    catalog_service = GeospatialCatalogService(
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
    )
    return GeospatialRuntime(
        api_service=GeospatialApiService(
            catalog_service=catalog_service,
            manifest_loader=manifest_loader,
            runtime_registry=runtime_registry,
            provider_registry=ProviderRegistry(manifest_loader=manifest_loader),
        )
    )
