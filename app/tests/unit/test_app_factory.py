from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import server.app as app_module
from server.common.paths import FASTAPI_API_PREFIX


###############################################################################
def _settings():  # noqa: ANN202
    return SimpleNamespace(
        database=SimpleNamespace(
            database_path="test.db",
        ),
        jobs=SimpleNamespace(polling_interval=1.0),
        credential_master_key="dev-key",
        credential_key_version="v1",
    )


###############################################################################
def _build_chat_runtime(call_order: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        agent_orchestrator=object(),
        conversation_repository=object(),
        history_service=object(),
        task_state_service=object(),
        settings_service=SimpleNamespace(
            get_settings=lambda: call_order.append("settings_service.get_settings")
        ),
        maintenance_service=SimpleNamespace(),
    )


###############################################################################
def _build_geospatial_runtime() -> SimpleNamespace:
    return SimpleNamespace(
        api_service=object(),
        capability_registry=object(),
        provider_registry=object(),
        credential_resolver=object(),
    )


###############################################################################
class _LifecycleStub:
    # -------------------------------------------------------------------------
    def __init__(self, call_order: list[str]) -> None:
        self.call_order = call_order

    # -------------------------------------------------------------------------
    async def shutdown(self) -> None:
        self.call_order.append("run_lifecycle.shutdown")


###############################################################################
def _response_schema_ref(schema: dict, path: str, method: str, status_code: str) -> str:
    response = schema["paths"][path][method]["responses"][status_code]
    return response["content"]["application/json"]["schema"]["$ref"]


###############################################################################
def test_create_app_exposes_expected_entrypoint(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)

    created = app_module.create_app()

    assert isinstance(created, FastAPI)
    route_paths = {route.path for route in created.routes}
    removed_maps_prefix = f"{FASTAPI_API_PREFIX}/" + "maps"
    assert f"{removed_maps_prefix}/search" not in route_paths
    assert f"{removed_maps_prefix}/catalog" not in route_paths
    assert f"{removed_maps_prefix}/jobs" not in route_paths
    assert f"{FASTAPI_API_PREFIX}/geospatial/capabilities" in route_paths
    assert (
        f"{FASTAPI_API_PREFIX}/geospatial/tiles/{{capability_id}}/{{z}}/{{x}}/{{y}}.png"
        in route_paths
    )
    assert f"{FASTAPI_API_PREFIX}/chat/turn" in route_paths
    assert f"{FASTAPI_API_PREFIX}/jobs/{{job_id}}" in route_paths
    assert f"{FASTAPI_API_PREFIX}/jobs/{{job_id}}/cancel" in route_paths


###############################################################################
def test_openapi_declares_stable_response_models(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)

    schema = app_module.create_app().openapi()

    assert schema["openapi"]
    assert (
        _response_schema_ref(
            schema, f"{FASTAPI_API_PREFIX}/conversations", "post", "201"
        )
        == "#/components/schemas/ConversationCreateResponse"
    )
    assert (
        _response_schema_ref(
            schema, f"{FASTAPI_API_PREFIX}/chat/settings", "get", "200"
        )
        == "#/components/schemas/ModelSettingsResponse"
    )
    assert (
        _response_schema_ref(schema, f"{FASTAPI_API_PREFIX}/chat/models", "get", "200")
        == "#/components/schemas/ModelLibraryResponse"
    )
    assert (
        _response_schema_ref(
            schema, f"{FASTAPI_API_PREFIX}/jobs/{{job_id}}", "get", "200"
        )
        == "#/components/schemas/BackgroundJobStatusResponse"
    )
    assert (
        _response_schema_ref(
            schema, f"{FASTAPI_API_PREFIX}/geospatial/capabilities", "get", "200"
        )
        == "#/components/schemas/GeospatialCatalogResponse"
    )
    stream_schema = schema["paths"][f"{FASTAPI_API_PREFIX}/chat/stream"]["post"][
        "responses"
    ]["200"]
    assert "$ref" not in str(stream_schema)
    assert schema["info"]["version"] == "1.0.0"


###############################################################################
def test_runtime_objects_are_attached_only_after_startup(monkeypatch) -> None:
    call_order: list[str] = []
    search_runtime = SimpleNamespace(
        search_orchestrator=SimpleNamespace(execute=lambda payload: payload),
    )
    chat_runtime = _build_chat_runtime(call_order)
    geospatial_runtime = _build_geospatial_runtime()
    job_service = SimpleNamespace(
        start=lambda: call_order.append("job_service.start"),
        stop=lambda: call_order.append("job_service.stop"),
    )

    monkeypatch.setattr(app_module, "get_server_settings", _settings)
    monkeypatch.setattr(app_module, "SQLiteRepository", lambda settings: object())
    monkeypatch.setattr(
        app_module,
        "initialize_database",
        lambda backend, **kwargs: call_order.append("initialize_database"),
    )
    monkeypatch.setattr(
        app_module,
        "build_search_runtime",
        lambda **kwargs: call_order.append("build_search_runtime") or search_runtime,
    )
    monkeypatch.setattr(
        app_module,
        "build_chat_runtime",
        lambda orchestrator, database, **kwargs: (
            call_order.append("build_chat_runtime") or chat_runtime
        ),
    )
    monkeypatch.setattr(
        app_module,
        "build_geospatial_runtime",
        lambda database: (
            call_order.append("build_geospatial_runtime") or geospatial_runtime
        ),
    )
    monkeypatch.setattr(
        app_module, "AgentRunEventRepository", lambda database: object()
    )
    monkeypatch.setattr(app_module, "AgentRunRepository", lambda database: object())
    monkeypatch.setattr(
        app_module, "AgentSteeringRepository", lambda database: object()
    )
    monkeypatch.setattr(app_module, "CredentialRepository", lambda database: object())
    monkeypatch.setattr(
        app_module, "BackgroundJobService", lambda **kwargs: job_service
    )
    monkeypatch.setattr(
        app_module, "ChatStreamingService", lambda orchestrator: object()
    )
    monkeypatch.setattr(
        app_module,
        "run_startup_validations",
        lambda credentials_repo: call_order.append("run_startup_validations"),
    )
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)

    created = app_module.create_app()

    with TestClient(created):
        assert created.state.search_runtime is search_runtime
        assert created.state.chat_runtime is chat_runtime
        assert created.state.geospatial_runtime is geospatial_runtime
        assert created.state.job_service is job_service

    assert call_order == [
        "initialize_database",
        "build_geospatial_runtime",
        "build_search_runtime",
        "build_chat_runtime",
        "job_service.start",
        "settings_service.get_settings",
        "run_startup_validations",
        "job_service.stop",
    ]


###############################################################################
def test_lifespan_cleanup_runs_when_startup_validation_fails(monkeypatch) -> None:
    call_order: list[str] = []
    search_runtime = SimpleNamespace(search_orchestrator=SimpleNamespace())
    chat_runtime = _build_chat_runtime(call_order)
    lifecycle = _LifecycleStub(call_order)
    geospatial_runtime = _build_geospatial_runtime()
    job_service = SimpleNamespace(
        start=lambda: call_order.append("job_service.start"),
        stop=lambda: call_order.append("job_service.stop"),
    )

    monkeypatch.setattr(app_module, "get_server_settings", _settings)
    monkeypatch.setattr(app_module, "SQLiteRepository", lambda settings: object())
    monkeypatch.setattr(
        app_module, "initialize_database", lambda backend, **kwargs: None
    )
    monkeypatch.setattr(
        app_module, "build_search_runtime", lambda **_kwargs: search_runtime
    )
    monkeypatch.setattr(
        app_module,
        "build_chat_runtime",
        lambda orchestrator, database, **kwargs: chat_runtime,
    )
    monkeypatch.setattr(
        app_module, "build_geospatial_runtime", lambda database: geospatial_runtime
    )
    monkeypatch.setattr(
        app_module, "AgentRunEventRepository", lambda database: object()
    )
    monkeypatch.setattr(app_module, "AgentRunRepository", lambda database: object())
    monkeypatch.setattr(
        app_module, "AgentSteeringRepository", lambda database: object()
    )
    monkeypatch.setattr(app_module, "CredentialRepository", lambda database: object())
    monkeypatch.setattr(app_module, "RunLifecycleService", lambda **kwargs: lifecycle)
    monkeypatch.setattr(
        app_module, "BackgroundJobService", lambda **kwargs: job_service
    )
    monkeypatch.setattr(
        app_module, "ChatStreamingService", lambda orchestrator: object()
    )
    monkeypatch.setattr(
        app_module,
        "run_startup_validations",
        lambda credentials_repo: (_ for _ in ()).throw(RuntimeError("startup failure")),
    )
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)

    with pytest.raises(RuntimeError, match="startup failure"):
        with TestClient(app_module.create_app()):
            pass

    assert call_order == [
        "job_service.start",
        "settings_service.get_settings",
        "job_service.stop",
        "run_lifecycle.shutdown",
    ]
