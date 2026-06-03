from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.app as app_module
from server.common.constants import FASTAPI_API_PREFIX


def _settings():  # noqa: ANN202
    return SimpleNamespace(
        database=SimpleNamespace(database_path="test.db", insert_batch_size=1000),
        credential_master_key="dev-key",
        credential_key_version="v1",
    )


def _build_chat_runtime(call_order: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        settings_service=SimpleNamespace(
            get_settings=lambda: call_order.append("settings_service.get_settings")
        ),
        maintenance_service=SimpleNamespace(),
    )


def _mock_lifespan_dependencies(monkeypatch) -> None:
    search_runtime = SimpleNamespace(search_orchestrator=object())
    chat_runtime = _build_chat_runtime([])

    monkeypatch.setattr(app_module, "get_server_settings", _settings)
    monkeypatch.setattr(app_module, "initialize_database", lambda settings: None)
    monkeypatch.setattr(app_module, "build_search_runtime", lambda: search_runtime)
    monkeypatch.setattr(
        app_module, "build_chat_runtime", lambda orchestrator: chat_runtime
    )
    monkeypatch.setattr(app_module, "run_startup_validations", lambda settings: None)


def test_client_build_available_uses_index_file(monkeypatch, tmp_path) -> None:
    index_path = tmp_path / "index.html"
    monkeypatch.setattr(app_module, "CLIENT_INDEX_FILE_PATH", str(index_path))
    assert app_module._client_build_available() is False

    index_path.write_text("<html></html>", encoding="utf-8")
    assert app_module._client_build_available() is True


def test_create_app_exposes_expected_entrypoint(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)

    created = app_module.create_app()

    assert isinstance(created, FastAPI)
    assert isinstance(app_module.app, FastAPI)
    route_paths = {route.path for route in created.routes}
    assert f"{FASTAPI_API_PREFIX}/maps/search" in route_paths
    assert f"{FASTAPI_API_PREFIX}/chat/turn" in route_paths
    assert f"{FASTAPI_API_PREFIX}/geospatial/capabilities" in route_paths


def test_runtime_objects_are_attached_only_after_startup(monkeypatch) -> None:
    call_order: list[str] = []
    search_runtime = SimpleNamespace(search_orchestrator=object())
    chat_runtime = _build_chat_runtime(call_order)

    monkeypatch.setattr(app_module, "get_server_settings", _settings)
    monkeypatch.setattr(
        app_module,
        "initialize_database",
        lambda settings: call_order.append("initialize_database"),
    )
    monkeypatch.setattr(
        app_module,
        "build_search_runtime",
        lambda: call_order.append("build_search_runtime") or search_runtime,
    )
    monkeypatch.setattr(
        app_module,
        "build_chat_runtime",
        lambda orchestrator: call_order.append("build_chat_runtime") or chat_runtime,
    )
    monkeypatch.setattr(
        app_module,
        "run_startup_validations",
        lambda settings: call_order.append("run_startup_validations"),
    )

    created = app_module.create_app()
    assert not hasattr(created.state, "search_runtime")
    assert not hasattr(created.state, "chat_runtime")

    with TestClient(created):
        assert created.state.search_runtime is search_runtime
        assert created.state.chat_runtime is chat_runtime

    assert call_order == [
        "initialize_database",
        "build_search_runtime",
        "build_chat_runtime",
        "settings_service.get_settings",
        "run_startup_validations",
    ]


def test_access_keys_router_is_not_registered(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)
    created = app_module.create_app()
    route_paths = {route.path for route in created.routes}
    assert f"{FASTAPI_API_PREFIX}/access-keys" not in route_paths
    assert f"{FASTAPI_API_PREFIX}/access-keys/{{key_id}}" not in route_paths


def test_create_app_redirects_root_to_docs_without_client_build(monkeypatch) -> None:
    _mock_lifespan_dependencies(monkeypatch)
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)

    with TestClient(app_module.create_app()) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code in {302, 307}
    assert response.headers["location"] == "/docs"


def test_create_app_serves_index_when_client_build_exists(monkeypatch, tmp_path) -> None:
    index_path = tmp_path / "index.html"
    index_path.write_text("<html>spa</html>", encoding="utf-8")

    _mock_lifespan_dependencies(monkeypatch)
    monkeypatch.setattr(app_module, "_client_build_available", lambda: True)
    monkeypatch.setattr(app_module, "CLIENT_INDEX_FILE_PATH", str(index_path))
    monkeypatch.setattr(app_module, "CLIENT_ASSETS_PATH", str(tmp_path / "assets"))

    with TestClient(app_module.create_app()) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "spa" in response.text


def test_resolve_client_file_blocks_path_traversal(monkeypatch, tmp_path) -> None:
    client_root = tmp_path / "browser"
    client_root.mkdir()
    safe_file = client_root / "main.js"
    safe_file.write_text("console.log('ok')", encoding="utf-8")

    monkeypatch.setattr(app_module, "CLIENT_DIST_PATH", str(client_root))

    assert app_module._resolve_client_file("main.js") == safe_file.resolve()
    assert app_module._resolve_client_file("../outside.txt") is None


def test_create_app_serves_existing_client_file(monkeypatch, tmp_path) -> None:
    client_root = tmp_path / "browser"
    assets_dir = client_root / "assets"
    assets_dir.mkdir(parents=True)
    index_path = client_root / "index.html"
    js_path = client_root / "main.js"
    index_path.write_text("<html>spa</html>", encoding="utf-8")
    js_path.write_text("console.log('asset')", encoding="utf-8")

    _mock_lifespan_dependencies(monkeypatch)
    monkeypatch.setattr(app_module, "_client_build_available", lambda: True)
    monkeypatch.setattr(app_module, "CLIENT_DIST_PATH", str(client_root))
    monkeypatch.setattr(app_module, "CLIENT_INDEX_FILE_PATH", str(index_path))
    monkeypatch.setattr(app_module, "CLIENT_ASSETS_PATH", str(assets_dir))

    with TestClient(app_module.create_app()) as client:
        response = client.get("/main.js")

    assert response.status_code == 200
    assert "asset" in response.text


def test_create_app_falls_back_to_index_for_spa_routes(monkeypatch, tmp_path) -> None:
    client_root = tmp_path / "browser"
    assets_dir = client_root / "assets"
    assets_dir.mkdir(parents=True)
    index_path = client_root / "index.html"
    index_path.write_text("<html>spa-shell</html>", encoding="utf-8")

    _mock_lifespan_dependencies(monkeypatch)
    monkeypatch.setattr(app_module, "_client_build_available", lambda: True)
    monkeypatch.setattr(app_module, "CLIENT_DIST_PATH", str(client_root))
    monkeypatch.setattr(app_module, "CLIENT_INDEX_FILE_PATH", str(index_path))
    monkeypatch.setattr(app_module, "CLIENT_ASSETS_PATH", str(assets_dir))

    with TestClient(app_module.create_app()) as client:
        response = client.get("/deep/link")

    assert response.status_code == 200
    assert "spa-shell" in response.text


def test_openapi_schema_generates(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "_client_build_available", lambda: False)

    created = app_module.create_app()
    schema = created.openapi()

    assert "paths" in schema
    paths = schema["paths"]
    assert f"{FASTAPI_API_PREFIX}/maps/search" in paths
    assert f"{FASTAPI_API_PREFIX}/geospatial/capabilities" in paths
    assert f"{FASTAPI_API_PREFIX}/chat/settings" in paths
