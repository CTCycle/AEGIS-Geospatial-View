from __future__ import annotations

from server.repositories.credential_material import seed_credential_encryption_material
from server.services.geospatial.api_service import GeospatialApiService
from server.services.geospatial.composition import (
    GeospatialRuntime,
    build_geospatial_runtime,
)

###############################################################################
def test_build_geospatial_runtime_reuses_shared_services(sqlite_backend) -> None:
    seed_credential_encryption_material(sqlite_backend)
    runtime = build_geospatial_runtime(sqlite_backend)

    assert isinstance(runtime, GeospatialRuntime)
    assert isinstance(runtime.api_service, GeospatialApiService)
    assert runtime.api_service.catalog_service.capability_registry is not None
    assert (
        runtime.api_service.catalog_service.capability_registry.manifest_loader
        is runtime.api_service.manifest_loader
    )
    assert (
        runtime.api_service.catalog_service.runtime_registry
        is runtime.api_service.runtime_registry
    )
    assert (
        runtime.api_service.provider_registry.manifest_loader
        is runtime.api_service.manifest_loader
    )
