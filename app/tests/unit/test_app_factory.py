from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.app as app_module
from server.common.paths import FASTAPI_API_PREFIX


###############################################################################
def _settings():  # noqa: ANN202
    return SimpleNamespace(
        database=SimpleNamespace(database_path="test.db", insert_batch_size=1000),
        jobs=SimpleNamespace(polling_interval=1.0),
        credential_master_key="dev-key",
        credential_key_version="v1",
    )


###############################################################################
def _build_chat_runtime(call_order: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        agent_orchestrator=object(),
        settings_service=SimpleNamespace(
            get_settings=lambda: call_order.append("settings_service.get_settings")
        ),
        maintenance_service=SimpleNamespace(),
    )


###############################################################################
def _build_geospatial_runtime() -> SimpleNamespace:
    return SimpleNamespace(api_service=object())


###############################################################################
def test_create_app_exposes_expected_entrypoint(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)

    created = app_module.create_app()

    assert isinstance(created, FastAPI)
    route_paths = {route.path for route in created.routes}
    assert f"{FASTAPI_API_PREFIX}/maps/search" in route_paths
    assert f"{FASTAPI_API_PREFIX}/chat/turn" in route_paths
    assert f"{FASTAPI_API_PREFIX}/jobs/{{job_id}}" in route_paths


###############################################################################
def test_runtime_objects_are_attached_only_after_startup(monkeypatch) -> None:
    call_order: list[str] = []
    search_runtime = SimpleNamespace(
        search_orchestrator=object(),
        search_execution=SimpleNamespace(
            orchestrator=SimpleNamespace(execute=lambda payload: payload)
        ),
    )
    chat_runtime = _build_chat_runtime(call_order)
    geospatial_runtime = _build_geospatial_runtime()
    job_service = SimpleNamespace(
        start=lambda: call_order.append("job_service.start"),
        stop=lambda: call_order.append("job_service.stop"),
    )

    monkeypatch.setattr(app_module, "get_server_settings", _settings)
    monkeypatch.setattr(app_module, "initialize_database", lambda backend: call_order.append("initialize_database"))
    monkeypatch.setattr(app_module, "seed_reference_catalog", lambda backend: None)
    monkeypatch.setattr(app_module, "build_search_runtime", lambda: call_order.append("build_search_runtime") or search_runtime)
    monkeypatch.setattr(app_module, "build_chat_runtime", lambda orchestrator: call_order.append("build_chat_runtime") or chat_runtime)
    monkeypatch.setattr(app_module, "build_geospatial_runtime", lambda: call_order.append("build_geospatial_runtime") or geospatial_runtime)
    monkeypatch.setattr(app_module, "BackgroundJobService", lambda **kwargs: job_service)
    monkeypatch.setattr(app_module, "ChatStreamingService", lambda orchestrator: object())
    monkeypatch.setattr(app_module, "run_startup_validations", lambda settings: call_order.append("run_startup_validations"))
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)

    created = app_module.create_app()

    with TestClient(created):
        assert created.state.search_runtime is search_runtime
        assert created.state.chat_runtime is chat_runtime
        assert created.state.geospatial_runtime is geospatial_runtime
        assert created.state.job_service is job_service

    assert call_order == [
        "initialize_database",
        "build_search_runtime",
        "build_chat_runtime",
        "build_geospatial_runtime",
        "job_service.start",
        "settings_service.get_settings",
        "run_startup_validations",
        "job_service.stop",
    ]
