from __future__ import annotations

from server.repositories.credential_material import seed_credential_encryption_material
from server.services.geospatial.api_service import GeospatialApiService
from server.services.geospatial.composition import (
    GeospatialRuntime,
    build_geospatial_runtime,
)
from server.services.search.composition import build_search_runtime
from server.services.chat.composition import build_chat_runtime


###############################################################################
def test_build_geospatial_runtime_reuses_shared_services(sqlite_backend) -> None:
    seed_credential_encryption_material(sqlite_backend)
    runtime = build_geospatial_runtime(sqlite_backend)

    assert isinstance(runtime, GeospatialRuntime)
    assert isinstance(runtime.api_service, GeospatialApiService)
    assert runtime.api_service.catalog_service.capability_registry is not None
    assert runtime.api_service.catalog_snapshot is runtime.catalog_snapshot
    assert (
        runtime.api_service.catalog_service.runtime_registry
        is runtime.api_service.runtime_registry
    )
    assert (
        runtime.api_service.catalog_service.capability_registry.catalog_snapshot
        is runtime.catalog_snapshot
    )
    assert (
        runtime.api_service.provider_registry.catalog_snapshot
        is runtime.catalog_snapshot
    )


###############################################################################
def test_search_and_chat_consume_shared_geospatial_runtime(sqlite_backend) -> None:
    seed_credential_encryption_material(sqlite_backend)
    geospatial_runtime = build_geospatial_runtime(sqlite_backend)
    search_runtime = build_search_runtime(
        capability_registry=geospatial_runtime.capability_registry,
        provider_registry=geospatial_runtime.provider_registry,
        credential_resolver=geospatial_runtime.credential_resolver,
    )
    chat_runtime = build_chat_runtime(
        search_runtime.search_orchestrator,
        sqlite_backend,
        geospatial_runtime=geospatial_runtime,
    )

    assert search_runtime.capability_registry is geospatial_runtime.capability_registry
    assert search_runtime.provider_registry is geospatial_runtime.provider_registry
    assert (
        search_runtime.search_orchestrator.render_descriptor_service.provider_registry
        is geospatial_runtime.provider_registry
    )
    assert (
        chat_runtime.agent_orchestrator.policy_engine.capability_registry
        is geospatial_runtime.capability_registry
    )
    assert (
        chat_runtime.agent_orchestrator.policy_engine.runtime_registry
        is geospatial_runtime.runtime_registry
    )
    assert (
        chat_runtime.agent_orchestrator.tool_registry.runtime_registry
        is geospatial_runtime.runtime_registry
    )
