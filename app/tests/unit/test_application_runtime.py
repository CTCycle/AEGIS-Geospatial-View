from __future__ import annotations
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import server.app as app_module
import json
import sqlite3
import os
import importlib
import subprocess
import sys
import tomllib
from server.common.paths import FASTAPI_API_PREFIX
from pathlib import Path
from typing import Any
from tests.e2e.helpers.network_capture import NetworkCapture, observed_page
from tests.e2e.test_live_raster_diagnostics import _raster_transport as raster_transport
from tests.e2e.test_route_matrix_live import _raster_transport as route_transport
from sqlalchemy.orm import Session
from server.configurations.settings import AppSettings, DatabaseSettings
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.runtime_settings import RuntimeSettingsRepository
from server.repositories.schemas import Base
from server.configurations.environment import ensure_environment_loaded, reset_environment_bootstrap_for_tests
from server.api.settings import router
from server.services.settings.runtime_settings import RuntimeSettingsService

# --- test_app_factory.py ---




###############################################################################
def _settings():  # noqa: ANN202
    return SimpleNamespace(
        database=SimpleNamespace(
            database_path="test.db",
        ),
        credential_master_key="dev-key",
        credential_key_version="v1",
    )

###############################################################################
def _build_chat_runtime(call_order: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        agent_orchestrator=object(),
        conversation_repository=object(),
        history_service=object(),
        settings_service=SimpleNamespace(
            validate_persisted_settings=lambda: call_order.append(
                "settings_service.validate_persisted_settings"
            )
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
        catalog_snapshot=object(),
    )

###############################################################################
class _LifecycleStub:

    # -------------------------------------------------------------------------
    def __init__(self, call_order: list[str]) -> None:
        self.call_order = call_order

    # -------------------------------------------------------------------------
    def resume_active_runs(self) -> None:
        self.call_order.append("run_lifecycle.resume_active_runs")

    # -------------------------------------------------------------------------
    async def shutdown(self) -> None:
        self.call_order.append("run_lifecycle.shutdown")


###############################################################################
async def _record_async(call_order: list[str], label: str) -> None:
    call_order.append(label)

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
    assert f"{FASTAPI_API_PREFIX}/settings/runtime" in route_paths

###############################################################################
def test_create_app_uses_only_canonical_router_composition(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)

    created = app_module.create_app()
    route_paths = {route.path for route in created.routes}

    assert f"{FASTAPI_API_PREFIX}/health" in route_paths
    assert f"{FASTAPI_API_PREFIX}/chat/turn" in route_paths
    assert f"{FASTAPI_API_PREFIX}/conversations" in route_paths
    assert (
        f"{FASTAPI_API_PREFIX}/conversations/{{conversation_id}}/realtime"
        in route_paths
    )
    assert f"{FASTAPI_API_PREFIX}/realtime/metrics" in route_paths
    assert f"{FASTAPI_API_PREFIX}/geospatial/capabilities" in route_paths
    assert f"{FASTAPI_API_PREFIX}/settings/runtime" in route_paths

    shadow_prefixes = ("/api/maps", "/api/preview", "/api/legacy", "/api/shadow")
    assert not any(
        path == prefix or path.startswith(f"{prefix}/")
        for path in route_paths
        for prefix in shadow_prefixes
    )

    response = TestClient(created).get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"

###############################################################################
def test_create_app_mounts_client_root_assets_and_spa_fallback(
    monkeypatch,
    tmp_path,
) -> None:
    client_dist = tmp_path / "dist"
    client_assets = client_dist / "assets"
    client_assets.mkdir(parents=True)
    index_file = client_dist / "index.html"
    index_file.write_text("<html>client</html>", encoding="utf-8")
    asset_file = client_assets / "main.js"
    asset_file.write_text("console.log('client');", encoding="utf-8")

    monkeypatch.setattr(app_module, "_client_build_available", lambda: True)
    monkeypatch.setattr(app_module, "CLIENT_DIST_PATH", client_dist)
    monkeypatch.setattr(app_module, "CLIENT_ASSETS_PATH", client_assets)
    monkeypatch.setattr(app_module, "CLIENT_INDEX_FILE_PATH", index_file)

    with TestClient(app_module.create_app()) as client:
        root = client.get("/")
        asset = client.get("/assets/main.js")
        fallback = client.get("/map/rome")
        unknown_api = client.get(f"{FASTAPI_API_PREFIX}/missing")

    assert unknown_api.status_code == 404
    assert root.status_code == 200
    assert root.text == "<html>client</html>"
    assert asset.status_code == 200
    assert "console.log" in asset.text
    assert fallback.status_code == 200
    assert fallback.text == "<html>client</html>"

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
        _response_schema_ref(
            schema, f"{FASTAPI_API_PREFIX}/settings/runtime", "get", "200"
        )
        == "#/components/schemas/RuntimeSettingsResponse"
    )
    assert (
        _response_schema_ref(schema, f"{FASTAPI_API_PREFIX}/chat/models", "get", "200")
        == "#/components/schemas/ModelLibraryResponse"
    )
    assert (
        _response_schema_ref(
            schema, f"{FASTAPI_API_PREFIX}/geospatial/capabilities", "get", "200"
        )
        == "#/components/schemas/GeospatialCatalogResponse"
    )
    assert schema["info"]["version"] == "1.0.0"

###############################################################################
def test_runtime_objects_are_attached_only_after_startup(monkeypatch) -> None:
    call_order: list[str] = []
    chat_runtime = _build_chat_runtime(call_order)
    geospatial_runtime = _build_geospatial_runtime()
    database = SimpleNamespace(
        engine=SimpleNamespace(
            dispose=lambda: call_order.append("sqlite.dispose"),
        )
    )
    realtime_connections = SimpleNamespace(
        close_all=lambda: _record_async(call_order, "realtime.close_all"),
    )

    monkeypatch.setattr(app_module, "ensure_environment_loaded", lambda: None)
    monkeypatch.setattr(
        app_module,
        "load_database_configuration",
        lambda: SimpleNamespace(
            database_path="test.db",
            sqlite_lock_timeout_seconds=5,
            backend="sqlite",
        ),
    )
    monkeypatch.setattr(
        app_module,
        "RuntimeSettingsRepository",
        lambda database: SimpleNamespace(
            get_required=lambda: SimpleNamespace(
                to_server_settings=lambda database_settings: _settings()
            )
        ),
    )
    monkeypatch.setattr(app_module, "RuntimeSettingsService", lambda repository: object())
    monkeypatch.setattr(app_module, "SQLiteRepository", lambda settings: database)
    monkeypatch.setattr(
        app_module,
        "initialize_database",
        lambda backend, **kwargs: call_order.append("initialize_database"),
    )
    monkeypatch.setattr(
        app_module,
        "build_chat_runtime",
        lambda database, **kwargs: (
            call_order.append("build_chat_runtime") or chat_runtime
        ),
    )
    monkeypatch.setattr(
        app_module,
        "build_geospatial_runtime",
        lambda database, **kwargs: (
            call_order.append("build_geospatial_runtime") or geospatial_runtime
        ),
    )
    monkeypatch.setattr(
        app_module, "AgentRunEventRepository", lambda database: object()
    )
    monkeypatch.setattr(
        app_module,
        "AgentRunRepository",
        lambda database, **_kwargs: SimpleNamespace(list_resumable_runs=lambda: []),
    )
    monkeypatch.setattr(
        app_module, "AgentSteeringRepository", lambda database: object()
    )
    monkeypatch.setattr(
        app_module, "RunLifecycleService", lambda **kwargs: _LifecycleStub(call_order)
    )
    monkeypatch.setattr(
        app_module,
        "RealtimeConnectionRegistry",
        lambda: realtime_connections,
    )
    monkeypatch.setattr(
        app_module,
        "run_startup_validations",
        lambda snapshot: (
            call_order.append("run_startup_validations")
            if snapshot is geospatial_runtime.catalog_snapshot
            else (_ for _ in ()).throw(AssertionError("startup snapshot was not shared"))
        ),
    )
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)

    created = app_module.create_app()

    with TestClient(created):
        assert created.state.chat_runtime is chat_runtime
        assert created.state.geospatial_runtime is geospatial_runtime

    assert call_order == [
        "initialize_database",
        "build_geospatial_runtime",
        "build_chat_runtime",
        "settings_service.validate_persisted_settings",
        "run_startup_validations",
        "run_lifecycle.resume_active_runs",
        "realtime.close_all",
        "run_lifecycle.shutdown",
        "sqlite.dispose",
    ]

###############################################################################
def test_lifespan_cleanup_runs_when_startup_validation_fails(monkeypatch) -> None:
    call_order: list[str] = []
    chat_runtime = _build_chat_runtime(call_order)
    lifecycle = _LifecycleStub(call_order)
    geospatial_runtime = _build_geospatial_runtime()

    monkeypatch.setattr(app_module, "ensure_environment_loaded", lambda: None)
    monkeypatch.setattr(
        app_module,
        "load_database_configuration",
        lambda: SimpleNamespace(
            database_path="test.db",
            sqlite_lock_timeout_seconds=5,
            backend="sqlite",
        ),
    )
    monkeypatch.setattr(
        app_module,
        "RuntimeSettingsRepository",
        lambda database: SimpleNamespace(
            get_required=lambda: SimpleNamespace(
                to_server_settings=lambda database_settings: _settings()
            )
        ),
    )
    monkeypatch.setattr(app_module, "RuntimeSettingsService", lambda repository: object())
    monkeypatch.setattr(app_module, "SQLiteRepository", lambda settings: object())
    monkeypatch.setattr(
        app_module, "initialize_database", lambda backend, **kwargs: None
    )
    monkeypatch.setattr(
        app_module,
        "build_chat_runtime",
        lambda database, **kwargs: chat_runtime,
    )
    monkeypatch.setattr(
        app_module,
        "build_geospatial_runtime",
        lambda database, **kwargs: geospatial_runtime,
    )
    monkeypatch.setattr(
        app_module, "AgentRunEventRepository", lambda database: object()
    )
    monkeypatch.setattr(
        app_module, "AgentRunRepository", lambda database, **_kwargs: object()
    )
    monkeypatch.setattr(
        app_module, "AgentSteeringRepository", lambda database: object()
    )
    monkeypatch.setattr(app_module, "RunLifecycleService", lambda **kwargs: lifecycle)
    monkeypatch.setattr(
        app_module,
        "run_startup_validations",
        lambda snapshot: (_ for _ in ()).throw(RuntimeError("startup failure")),
    )
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)

    with pytest.raises(RuntimeError, match="startup failure"):
        with TestClient(app_module.create_app()):
            pass

    assert call_order == [
        "settings_service.validate_persisted_settings",
        "run_lifecycle.shutdown",
    ]

# --- test_browser_network_capture.py ---

"""Prevent truncated browser samples from producing false zero-request proof."""





###############################################################################
def test_request_counts_survive_event_truncation() -> None:
    capture = NetworkCapture(max_events=1)
    capture._append(
        {
            "kind": "response",
            "url": "https://localhost/api/geospatial/tiles/test/1/0/0.png",
        }
    )
    capture._append(
        {
            "kind": "request",
            "transport": "aegis_proxy",
            "capability_id": "eea_noise_end2022",
            "url": "http://localhost/api/geospatial/tiles/eea_noise_end2022/1/0/0.png",
        }
    )
    capture._append(
        {
            "kind": "request",
            "transport": "direct_upstream",
            "url": "https://noise.discomap.eea.europa.eu/tile",
        }
    )
    assert len(capture.events) == 1
    assert capture.summary()["dropped_events"] == 2
    assert capture.requests_by_host["noise.discomap.eea.europa.eu"] == 1
    assert capture.requests_by_transport == {"aegis_proxy": 1, "direct_upstream": 1}
    assert capture.proxy_requests_by_capability == {"eea_noise_end2022": 1}


###############################################################################
@pytest.mark.parametrize("transport", [raster_transport, route_transport])
def test_capture_recognizes_eea_and_fema_relay(transport: Any) -> None:
    for host in ("noise.discomap.eea.europa.eu", "hazards-fema.maps.arcgis.com"):
        assert transport(f"https://{host}/tile") == "direct_upstream"
        assert (
            transport(f"https://{host}/api/geospatial/tiles/test/1/0/0.png")
            == "direct_upstream"
        )


###############################################################################
def test_failed_scenario_saves_capture_and_closes_context(tmp_path: Path) -> None:
    calls: list[str] = []

    ###############################################################################
    class FakePage:

        # -------------------------------------------------------------------------
        def screenshot(self, **kwargs: Any) -> None:
            calls.append("failure_screenshot")

    ###############################################################################
    class FakeContext:

        # -------------------------------------------------------------------------
        def __enter__(self) -> "FakeContext":
            return self

        # -------------------------------------------------------------------------
        def __exit__(self, *args: Any) -> None:
            calls.append("closed")

        # -------------------------------------------------------------------------
        def route(self, *args: Any) -> None:
            calls.append("cache_disabled")

        # -------------------------------------------------------------------------
        def new_page(self) -> FakePage:
            return FakePage()

    ###############################################################################
    class FakeBrowser:

        # -------------------------------------------------------------------------
        def new_context(self, **kwargs: Any) -> FakeContext:
            assert kwargs["service_workers"] == "block"
            return FakeContext()

    ###############################################################################
    class Capture(NetworkCapture):

        # -------------------------------------------------------------------------
        def attach(self, page: Any) -> None:
            calls.append("attached")

    capture = Capture()
    output = tmp_path / "capture.json"
    with pytest.raises(RuntimeError):
        with observed_page(FakeBrowser(), capture, output):  # type: ignore[arg-type]
            calls.append("navigation")
            raise RuntimeError("private response must not enter capture")
    saved = json.loads(output.read_text())
    assert calls == [
        "cache_disabled",
        "attached",
        "navigation",
        "failure_screenshot",
        "closed",
    ]
    assert saved["observation"]["started_at"] <= saved["observation"]["ended_at"]
    assert saved["failure_type"] == "RuntimeError"
    assert "private response" not in output.read_text()

# --- test_configuration_management.py ---





###############################################################################
def _runtime_repository(tmp_path: Path) -> RuntimeSettingsRepository:
    database = SQLiteRepository(DatabaseSettings(str(tmp_path / "runtime.db")))
    Base.metadata.create_all(database.engine)
    return RuntimeSettingsRepository(database)


###############################################################################
def _runtime_row_count(tmp_path: Path) -> int:
    with sqlite3.connect(tmp_path / "runtime.db") as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM application_runtime_settings"
        ).fetchone()
    assert row is not None
    return int(row[0])


###############################################################################
def test_runtime_repository_seeds_database_defaults_once(tmp_path: Path) -> None:
    repository = _runtime_repository(tmp_path)

    settings = repository.initialize_defaults()
    restarted = repository.initialize_defaults()

    assert settings.runtime_payload() == AppSettings().runtime_payload()
    assert restarted == settings
    assert _runtime_row_count(tmp_path) == 1


###############################################################################
def test_runtime_repository_rolls_back_failed_settings_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repository = _runtime_repository(tmp_path)

    def fail_commit(_session: Session) -> None:
        raise RuntimeError("injected settings commit failure")

    monkeypatch.setattr(Session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="injected settings commit failure"):
        repository.initialize_defaults()

    assert repository.get() is None
    assert _runtime_row_count(tmp_path) == 0


###############################################################################
def test_existing_runtime_row_remains_authoritative(tmp_path: Path) -> None:
    repository = _runtime_repository(tmp_path)
    repository.initialize_defaults()
    updated = repository.update({"map": {"tiles": "CartoDB Positron"}})

    reloaded = repository.initialize_defaults()

    assert reloaded == updated
    assert reloaded.map.tiles == "CartoDB Positron"
    assert _runtime_row_count(tmp_path) == 1


###############################################################################
def test_runtime_repository_updates_one_block_atomically(tmp_path: Path) -> None:
    repository = _runtime_repository(tmp_path)
    repository.initialize_defaults()

    updated = repository.update({"map": {"tiles": "CartoDB Positron"}})
    assert updated.map.tiles == "CartoDB Positron"

    with pytest.raises(ValueError, match="Unsupported runtime settings in map"):
        repository.update({"map": {"unknown_tiles": "ignored"}})

    assert repository.get_required().map.tiles == "CartoDB Positron"


###############################################################################
def test_agent_execution_vision_policy_defaults_and_round_trip() -> None:
    defaults = AppSettings().agent_execution
    assert defaults.vision_policy == "disabled"
    assert defaults.vision_max_calls == 2

    payload = AppSettings().runtime_payload()
    payload["agent_execution"]["vision_policy"] = "on_failure"
    payload["agent_execution"]["vision_max_calls"] = 4
    reloaded = AppSettings.model_validate(payload)
    assert reloaded.agent_execution.vision_policy == "on_failure"
    assert reloaded.agent_execution.vision_max_calls == 4

    server_settings = reloaded.to_server_settings(DatabaseSettings(":memory:"))
    assert server_settings.agent_execution.vision_policy == "on_failure"
    assert server_settings.agent_execution.vision_max_calls == 4


###############################################################################
def test_agent_execution_rejects_unknown_vision_policy() -> None:
    payload = AppSettings().runtime_payload()
    payload["agent_execution"]["vision_policy"] = "sometimes"
    with pytest.raises(Exception):
        AppSettings.model_validate(payload)

# --- test_runtime_env_loading.py ---




###############################################################################
def test_runtime_env_is_loaded_from_dotenv(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "FASTAPI_HOST=127.0.0.1",
                "FASTAPI_PORT=6100",
                "UI_HOST=127.0.0.1",
                "UI_PORT=4980",
                "KERAS_BACKEND=tensorflow",
                "MPLBACKEND=Agg",
            ]
        ),
        encoding="utf-8",
    )

    for key in (
        "FASTAPI_HOST",
        "FASTAPI_PORT",
        "UI_HOST",
        "UI_PORT",
        "KERAS_BACKEND",
        "MPLBACKEND",
    ):
        monkeypatch.delenv(key, raising=False)

    reset_environment_bootstrap_for_tests()
    monkeypatch.setattr(
        "server.configurations.environment.ENV_FILE_PATH", str(env_file)
    )
    ensure_environment_loaded()

    assert os.getenv("FASTAPI_HOST") == "127.0.0.1"
    assert os.getenv("FASTAPI_PORT") == "6100"
    assert os.getenv("UI_HOST") == "127.0.0.1"
    assert os.getenv("UI_PORT") == "4980"
    assert os.getenv("KERAS_BACKEND") == "tensorflow"
    assert os.getenv("MPLBACKEND") == "Agg"

###############################################################################
def test_process_environment_values_are_not_overwritten(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("AEGIS_DATA_DIR=from-file\n", encoding="utf-8")
    monkeypatch.setenv("AEGIS_DATA_DIR", "from-process")
    monkeypatch.setattr(
        "server.configurations.environment.ENV_FILE_PATH", str(env_file)
    )
    reset_environment_bootstrap_for_tests()

    ensure_environment_loaded()

    assert os.getenv("AEGIS_DATA_DIR") == "from-process"

###############################################################################
def test_missing_runtime_env_is_created_from_example(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / "settings" / ".env"
    example_file = tmp_path / "settings" / ".env.example"
    example_file.parent.mkdir()
    example_file.write_bytes(b"FASTAPI_PORT=6101\r\n")

    monkeypatch.delenv("FASTAPI_PORT", raising=False)
    monkeypatch.setattr(
        "server.configurations.environment.ENV_FILE_PATH", str(env_file)
    )
    monkeypatch.setattr(
        "server.configurations.environment.ENV_EXAMPLE_FILE_PATH", str(example_file)
    )
    reset_environment_bootstrap_for_tests()

    loaded_path = ensure_environment_loaded()

    assert loaded_path == env_file
    assert env_file.read_bytes() == example_file.read_bytes()
    assert os.getenv("FASTAPI_PORT") == "6101"

###############################################################################
def test_existing_runtime_env_is_not_overwritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    existing = b"FASTAPI_PORT=6200\n"
    env_file.write_bytes(existing)
    example_file.write_bytes(b"FASTAPI_PORT=6300\n")

    monkeypatch.delenv("FASTAPI_PORT", raising=False)
    monkeypatch.setattr(
        "server.configurations.environment.ENV_FILE_PATH", str(env_file)
    )
    monkeypatch.setattr(
        "server.configurations.environment.ENV_EXAMPLE_FILE_PATH", str(example_file)
    )
    reset_environment_bootstrap_for_tests()

    ensure_environment_loaded()

    assert env_file.read_bytes() == existing
    assert os.getenv("FASTAPI_PORT") == "6200"

# --- test_runtime_settings_api.py ---





###############################################################################
def _client(tmp_path: Path) -> tuple[TestClient, RuntimeSettingsRepository]:
    database = SQLiteRepository(DatabaseSettings(str(tmp_path / "runtime.db")))
    Base.metadata.create_all(database.engine)
    repository = RuntimeSettingsRepository(database)
    repository.initialize_defaults()
    application = FastAPI()
    application.include_router(router, prefix="/api")
    application.state.runtime_settings_service = RuntimeSettingsService(repository)
    return TestClient(application), repository


###############################################################################
def test_runtime_settings_api_returns_typed_blocks_and_restart_metadata(tmp_path: Path) -> None:
    client, repository = _client(tmp_path)

    response = client.get("/api/settings/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == 1
    assert payload["chat"]["max_history_messages"] == 12
    assert payload["agent_execution"]["max_iterations"] == 12
    assert payload["agent_execution"]["max_discovery_attempts"] == 2
    assert payload["restart_required"] is False
    assert "credentials" not in payload
    serialized = json.dumps(payload).casefold()
    assert not any(
        secret_field in serialized
        for secret_field in ("api_key", "password", "secret", "token")
    )
    assert repository.get_required().chat.max_history_messages == 12


###############################################################################
def test_runtime_settings_api_merges_partial_blocks_atomically(tmp_path: Path) -> None:
    client, repository = _client(tmp_path)

    response = client.patch(
        "/api/settings/runtime",
        json={"chat": {"max_history_messages": 24}},
    )

    assert response.status_code == 200
    assert response.json()["chat"]["max_history_messages"] == 24
    assert response.json()["restart_required"] is True
    assert repository.get_required().chat.max_history_messages == 24


###############################################################################
def test_restart_requirement_survives_get_and_clears_when_values_return_to_startup(
    tmp_path: Path,
) -> None:
    client, repository = _client(tmp_path)

    changed = client.patch(
        "/api/settings/runtime",
        json={"chat": {"max_history_messages": 24}},
    )
    assert changed.status_code == 200
    assert changed.json()["restart_required"] is True

    reloaded = client.get("/api/settings/runtime")
    assert reloaded.status_code == 200
    assert reloaded.json()["restart_required"] is True
    assert "Restart AEGIS" in reloaded.json()["message"]

    reverted = client.patch(
        "/api/settings/runtime",
        json={"chat": {"max_history_messages": 12}},
    )
    assert reverted.status_code == 200
    assert reverted.json()["restart_required"] is False
    assert client.get("/api/settings/runtime").json()["restart_required"] is False


###############################################################################
def test_runtime_settings_survive_database_reopen_after_patch(tmp_path: Path) -> None:
    database_path = tmp_path / "runtime-restart.db"
    database = SQLiteRepository(DatabaseSettings(str(database_path)))
    Base.metadata.create_all(database.engine)
    repository = RuntimeSettingsRepository(database)
    repository.initialize_defaults()
    application = FastAPI()
    application.include_router(router, prefix="/api")
    application.state.runtime_settings_service = RuntimeSettingsService(repository)
    client = TestClient(application)

    response = client.patch(
        "/api/settings/runtime",
        json={"chat": {"max_history_messages": 31}},
    )

    assert response.status_code == 200
    assert response.json()["chat"]["max_history_messages"] == 31
    client.close()
    database.engine.dispose()

    restarted_database = SQLiteRepository(DatabaseSettings(str(database_path)))
    restarted_repository = RuntimeSettingsRepository(restarted_database)
    assert restarted_repository.get_required().chat.max_history_messages == 31
    restarted_settings_service = RuntimeSettingsService(restarted_repository)
    restarted_settings = restarted_settings_service.get_settings()
    assert restarted_settings.chat.max_history_messages == 31
    assert restarted_settings.restart_required is False
    restarted_database.engine.dispose()


###############################################################################
def test_agent_policy_patch_applies_to_new_runs_and_rejects_invalid_values_atomically(tmp_path: Path) -> None:
    client, repository = _client(tmp_path)
    response = client.patch("/api/settings/runtime", json={"agent_execution": {"max_iterations": 7, "max_discovery_attempts": 5}})
    assert response.status_code == 200
    assert response.json()["restart_required"] is False
    assert repository.get_required().agent_execution.max_discovery_attempts == 5
    response = client.patch("/api/settings/runtime", json={"agent_execution": {"max_iterations": 8, "max_discovery_attempts": 0}})
    assert response.status_code == 400
    assert repository.get_required().agent_execution.max_iterations == 7


###############################################################################
def test_runtime_settings_api_rejects_unknown_nested_fields(tmp_path: Path) -> None:
    client, repository = _client(tmp_path)

    response = client.patch(
        "/api/settings/runtime",
        json={"map": {"legacy_tiles": "ignored"}},
    )

    assert response.status_code == 400
    assert "Unsupported runtime settings in map" in response.json()["detail"]
    assert repository.get_required().map.tiles == "OpenStreetMap"


###############################################################################
def test_runtime_settings_api_rejects_unknown_blocks(tmp_path: Path) -> None:
    client, repository = _client(tmp_path)

    response = client.patch(
        "/api/settings/runtime",
        json={"unsupported": {"enabled": True}},
    )

    assert response.status_code == 422
    assert repository.get_required().map.tiles == "OpenStreetMap"

# --- test_canonical_runtime_contract.py ---



REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPOSITORY_ROOT / "app"

###############################################################################
def test_launcher_has_one_canonical_backend_entrypoint() -> None:
    launcher = (REPOSITORY_ROOT / "start_on_windows.ps1").read_text(
        encoding="utf-8"
    )

    assert "$backendModule = 'server.app:app'" in launcher
    assert "$backendWorkingDirectory = $AppDir" in launcher
    assert "$env:PYTHONPATH = $AppDir" in launcher
    assert (
        "Start-Process -FilePath $venvPython -ArgumentList $backendArguments"
        in launcher
    )
    assert "app.server.app:app" not in launcher
    assert "Start-Process -FilePath 'cmd.exe'" not in launcher
    assert "/k" not in launcher

###############################################################################
def test_launcher_uses_confirmed_port_guard_and_process_aware_startup() -> None:
    launcher = (REPOSITORY_ROOT / "start_on_windows.ps1").read_text(
        encoding="utf-8"
    )

    def function_body(name: str) -> str:
        start = launcher.index(f"function {name}")
        end = launcher.find("\nfunction ", start + 1)
        return launcher[start:] if end < 0 else launcher[start:end]

    launch = function_body("Invoke-LaunchApplication")
    confirmation = function_body("Confirm-PortConflictTermination")
    conflicts = function_body("Resolve-LaunchPortConflicts")
    grouped_conflicts = function_body("Get-PortConflicts")
    health_wait = function_body("Wait-HttpHealth")

    assert "Stop-PortListeners" not in launch
    assert "taskkill.exe" not in launch
    assert launch.count("Resolve-LaunchPortConflicts") == 2
    assert "StartTimeUtcTicks" in confirmation
    assert "'unavailable'" in confirmation
    assert "no existing process was terminated" in confirmation
    assert confirmation.index("$unresolvedOwners") < confirmation.index("Read-Host")
    assert "Confirm-PortConflictTermination" in conflicts
    assert "HashSet[int]" in conflicts
    assert "Dictionary[int, object]" in grouped_conflicts
    assert "ContainsKey($processId)" in grouped_conflicts
    assert "importlib.import_module('server.app')" not in launch
    assert "[System.Diagnostics.Process]$Process" in health_wait
    assert "HasExited" in health_wait

###############################################################################
def test_launcher_separates_dependency_sync_from_build_state() -> None:
    launcher = (REPOSITORY_ROOT / "start_on_windows.ps1").read_text(
        encoding="utf-8"
    )
    package_json = json.loads(
        (APP_ROOT / "client" / "package.json").read_text(encoding="utf-8")
    )

    def function_body(name: str) -> str:
        start = launcher.index(f"function {name}")
        end = launcher.find("\nfunction ", start + 1)
        return launcher[start:] if end < 0 else launcher[start:end]

    launch = function_body("Invoke-LaunchApplication")
    install = function_body("Invoke-InstallOrUpdate")
    rebuild = function_body("Invoke-RebuildFrontend")

    assert "Sync-Dependencies -BuildFrontend $false" in launch
    assert "Ensure-FrontendBuildCurrent" in launch
    assert "-BuildFrontend $true" in install
    assert "Build-Frontend" in rebuild
    assert "ALWAYS_REBUILD" not in launcher
    assert "prebuild" in package_json["scripts"]
    assert "postbuild" in package_json["scripts"]
    assert "test:frontend-state" in package_json["scripts"]

###############################################################################
def test_old_import_root_is_rejected_when_only_app_is_on_pythonpath() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(APP_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib; importlib.import_module('app.server.app')",
        ],
        cwd=APP_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0

###############################################################################
def test_public_api_exposes_native_routes_without_shadow_or_legacy_routes() -> None:
    application = importlib.import_module("server.app").create_app()
    paths = {
        route.path
        for route in application.routes
        if isinstance(getattr(route, "path", None), str)
    }

    assert "/api/chat/turn" in paths
    assert "/api/chat/stream" not in paths
    assert "/api/chat/jobs" not in paths
    assert not any(path.startswith("/api/jobs/") for path in paths)
    assert not any(
        path in paths
        for path in (
            "/api/geospatial/layers/{layer_id}/health",
            "/api/geospatial/providers/{provider_id}/layers",
            "/api/geospatial/providers/{provider_id}/layers/{layer_id}",
            "/api/geospatial/cameras/{camera_id}",
            "/api/geospatial/providers/{provider_id}/account-setup",
            "/api/geospatial/audit",
        )
    )
    assert not any(
        marker in path.casefold()
        for path in paths
        for marker in ("/shadow", "/preview", "/legacy")
    )

    composition = (
        APP_ROOT / "server" / "services" / "chat" / "composition.py"
    ).read_text(encoding="utf-8").casefold()
    assert "nativeagentorchestrator" in composition
    assert "shadow" not in composition
    assert "legacy" not in composition

###############################################################################
def test_all_tooling_resolves_disposable_state_under_canonical_cache_root() -> None:
    launcher = (REPOSITORY_ROOT / "start_on_windows.ps1").read_text(
        encoding="utf-8"
    )
    batch_runner = (APP_ROOT / "tests" / "run_tests.bat").read_text(
        encoding="utf-8"
    )
    server_config = tomllib.loads(
        (APP_ROOT / "server" / "pyproject.toml").read_text(encoding="utf-8")
    )
    angular_config = json.loads(
        (APP_ROOT / "client" / "angular.json").read_text(encoding="utf-8")
    )
    karma_config = (APP_ROOT / "client" / "karma.conf.cjs").read_text(
        encoding="utf-8"
    )
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPOSITORY_ROOT / ".github" / "workflows").glob("*.yml")
    )
    vscode_launch = (REPOSITORY_ROOT / ".vscode" / "launch.json").read_text(
        encoding="utf-8"
    )
    gitignore_text = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")

    active_tooling_text = "\n".join(
        (
            launcher,
            batch_runner,
            karma_config,
            workflow_text,
            vscode_launch,
            gitignore_text,
        )
    ).replace("\\", "/")
    canonical_root = "runtimes/cache"
    assert canonical_root in active_tooling_text
    assert server_config["tool"]["pytest"]["ini_options"]["cache_dir"] == (
        "../../runtimes/cache/pytest"
    )
    assert server_config["tool"]["ruff"]["cache-dir"] == "../../runtimes/cache/ruff"
    assert angular_config["cli"]["cache"]["path"] == "../../runtimes/cache/angular"
    assert "../../runtimes/cache/coverage/aegis-client" in karma_config
    assert "enable-" + "cache:" not in workflow_text
    assert "cache:" + " npm" not in workflow_text
    assert "$ToolCacheDir" not in launcher
    assert "$LegacyCache" not in launcher
    assert "$LegacyUvCache" not in launcher
    assert "ValidateSet('Launch', 'ClearCache')" in launcher
    assert "Clear-ApplicationCache -SkipConfirmation -Strict" in launcher

    forbidden_fragments = (
        "/".join(("app", "tests", "cache")),
        "/".join(("assets", "cache")),
        "." + "pytest_cache",
        "." + "ruff_cache",
        "." + "tmp_pytest",
        "." + "angular",
    )
    for fragment in forbidden_fragments:
        assert fragment not in active_tooling_text

    dot_pytest_cache = "." + "pytest" + "_cache"
    dot_ruff_cache = "." + "ruff" + "_cache"
    dot_tmp_pytest = "." + "tmp" + "_pytest"
    obsolete_roots = (
        REPOSITORY_ROOT / "assets" / "cache",
        APP_ROOT / "tests" / "cache",
        APP_ROOT / "client" / ("." + "angular"),
        REPOSITORY_ROOT / dot_pytest_cache,
        REPOSITORY_ROOT / dot_ruff_cache,
        REPOSITORY_ROOT / dot_tmp_pytest,
        APP_ROOT / dot_pytest_cache,
        APP_ROOT / dot_ruff_cache,
        APP_ROOT / "server" / dot_pytest_cache,
        APP_ROOT / "server" / "app" / "tests" / "cache",
        APP_ROOT / "server" / (".pytest" + "-cache-gbif"),
        APP_ROOT / "server" / (".pytest" + "-cache-tiles"),
        APP_ROOT / "server" / (".pytest" + "-cache-typing"),
        APP_ROOT / (".pytest" + "-tmp-canonical-basemap"),
        APP_ROOT / (".pytest" + "-tmp-lane1-baseline"),
        APP_ROOT / (".pytest" + "-tmp-native-map"),
        APP_ROOT / (".pytest" + "-tmp-terrain-catalog"),
    )
    assert all(not path.exists() for path in obsolete_roots)