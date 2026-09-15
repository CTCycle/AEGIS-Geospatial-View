from __future__ import annotations

from types import SimpleNamespace

from server.repositories.credential_material import seed_credential_encryption_material
from server.services.geospatial.api_service import GeospatialApiService
from server.services.geospatial.composition import (
    GeospatialRuntime,
    build_provider_execution_policy,
    build_geospatial_runtime,
)
from server.services.chat.composition import build_chat_runtime

###############################################################################
def test_provider_policy_uses_source_timeout_floors() -> None:
    settings = SimpleNamespace(
        agent_execution=SimpleNamespace(
            provider_request_seconds=10.0,
            provider_max_attempts=2,
            retry_backoff_base_seconds=0.25,
            retry_backoff_max_seconds=2.0,
        ),
        nominatim=SimpleNamespace(timeout=12.0),
        openmeteo=SimpleNamespace(timeout=15.0),
        overpass=SimpleNamespace(timeout=20.0),
        rainviewer=SimpleNamespace(timeout=15.0),
        gibs=SimpleNamespace(timeout=20.0, layer_sync_timeout=30.0),
    )

    policy = build_provider_execution_policy(settings)

    assert policy.timeout_seconds == 10.0
    assert policy.provider_timeout_seconds == {
        "nominatim": 12.0,
        "openmeteo": 15.0,
        "overpass": 20.0,
        "rainviewer": 15.0,
        "gibs": 30.0,
    }

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
def test_chat_consumes_shared_geospatial_runtime(sqlite_backend) -> None:
    seed_credential_encryption_material(sqlite_backend)
    geospatial_runtime = build_geospatial_runtime(sqlite_backend)
    chat_runtime = build_chat_runtime(
        sqlite_backend,
        geospatial_runtime=geospatial_runtime,
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
    assert chat_runtime.agent_loop is chat_runtime.agent_orchestrator.agent_loop
    assert chat_runtime.agent_loop is not None
    assert (
        chat_runtime.agent_turn_runner
        is chat_runtime.agent_orchestrator.agent_turn_runner
    )
    assert chat_runtime.agent_turn_runner is not None
    assert {
        tool.definition.name
        for tool in chat_runtime.agent_loop.tool_registry._registered_tools.values()
    } == {
        "route_request",
        "resolve_geospatial_location",
        "discover_geospatial_capabilities",
        "discover_geospatial_provider_layers",
        "describe_geospatial_capability",
        "execute_geospatial_capability",
        "inspect_evidence",
        "transform_evidence",
        "apply_map_plan",
    }
