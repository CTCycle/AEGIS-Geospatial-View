from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import AEGIS.server.app as app_module


def _settings(embedded_database: bool = False, auto_sync: bool = False):  # noqa: ANN202
    return SimpleNamespace(
        database=SimpleNamespace(embedded_database=embedded_database),
        vectors=SimpleNamespace(auto_sync_on_start=auto_sync),
    )


def test_create_app_exposes_expected_entrypoint() -> None:
    created = app_module.create_app()
    assert isinstance(created, FastAPI)
    assert isinstance(app_module.app, FastAPI)
    route_paths = {route.path for route in created.routes}
    assert "/api/maps/search" in route_paths
    assert "/api/chat/turn" in route_paths


def test_runtime_objects_are_attached_only_after_startup(monkeypatch) -> None:
    search_runtime = SimpleNamespace(search_orchestrator=object())
    chat_runtime = SimpleNamespace()
    monkeypatch.setattr(app_module, "get_server_settings", lambda: _settings())
    monkeypatch.setattr(app_module, "build_search_runtime", lambda: search_runtime)
    monkeypatch.setattr(
        app_module, "build_chat_runtime", lambda orchestrator: chat_runtime
    )

    created = app_module.create_app()
    assert not hasattr(created.state, "search_runtime")
    assert not hasattr(created.state, "chat_runtime")

    with TestClient(created):
        assert created.state.search_runtime is search_runtime
        assert created.state.chat_runtime is chat_runtime


def test_access_keys_router_is_not_registered() -> None:
    created = app_module.create_app()
    route_paths = {route.path for route in created.routes}
    assert "/api/access-keys" not in route_paths
    assert "/api/access-keys/{key_id}" not in route_paths
