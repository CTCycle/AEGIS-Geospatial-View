from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.common.paths import DATABASE_FILE_PATH
from server.configurations import build_database_settings
from server.configurations.environment import (
    ensure_environment_loaded,
    reset_environment_bootstrap_for_tests,
)
from server.configurations.management import ConfigurationManager


###############################################################################
def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


###############################################################################
def test_database_settings_uses_constants_database_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "EMBEDDED_DATABASE",
        "DATABASE_URL",
        "DATABASE_ENGINE",
        "DATABASE_HOST",
        "DATABASE_PORT",
        "DATABASE_NAME",
        "DATABASE_USERNAME",
        "DATABASE_PASSWORD",
        "DATABASE_SSL",
        "DATABASE_SSL_CA",
        "DATABASE_CONNECT_TIMEOUT",
        "DATABASE_INSERT_BATCH_SIZE",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = build_database_settings()
    assert settings.database_path == str(DATABASE_FILE_PATH)
    assert settings.embedded_database is True


###############################################################################
def test_database_settings_reads_insert_batch_size_from_env_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_INSERT_BATCH_SIZE", "777")
    settings = build_database_settings()
    assert settings.insert_batch_size == 777


###############################################################################
def test_database_settings_reads_external_database_keys_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "DATABASE_ENGINE",
        "DATABASE_HOST",
        "DATABASE_NAME",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("EMBEDDED_DATABASE", "false")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://url-user:url-pass@url-host:6543/url-db"
    )
    monkeypatch.setenv("DATABASE_USERNAME", "env-user")
    monkeypatch.setenv("DATABASE_PASSWORD", "env-pass")
    monkeypatch.setenv("DATABASE_PORT", "7777")
    monkeypatch.setenv("DATABASE_SSL", "true")
    monkeypatch.setenv("DATABASE_SSL_CA", "/env/ca.pem")
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT", "55")
    monkeypatch.setenv("DATABASE_INSERT_BATCH_SIZE", "2200")

    settings = build_database_settings()

    assert settings.embedded_database is False
    assert settings.engine == "postgresql+psycopg"
    assert settings.host == "url-host"
    assert settings.port == 7777
    assert settings.database_name == "url-db"
    assert settings.username == "env-user"
    assert settings.password == "env-pass"
    assert settings.ssl is True
    assert settings.ssl_ca == "/env/ca.pem"
    assert settings.connect_timeout == 55
    assert settings.insert_batch_size == 2200


###############################################################################
def test_database_settings_ignores_json_database_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "EMBEDDED_DATABASE",
        "DATABASE_URL",
        "DATABASE_ENGINE",
        "DATABASE_HOST",
        "DATABASE_PORT",
        "DATABASE_NAME",
        "DATABASE_USERNAME",
        "DATABASE_PASSWORD",
        "DATABASE_SSL",
        "DATABASE_SSL_CA",
        "DATABASE_CONNECT_TIMEOUT",
        "DATABASE_INSERT_BATCH_SIZE",
    ):
        monkeypatch.delenv(key, raising=False)

    settings = build_database_settings()

    assert settings.database_path == str(DATABASE_FILE_PATH)
    assert settings.embedded_database is True
    assert settings.engine is None
    assert settings.host is None
    assert settings.port is None
    assert settings.database_name is None
    assert settings.username is None
    assert settings.password is None
    assert settings.ssl is False
    assert settings.ssl_ca is None
    assert settings.connect_timeout > 0
    assert settings.insert_batch_size > 0


###############################################################################
def test_configuration_manager_reads_database_settings_from_env_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_file = tmp_path / "configurations.json"
    env_file = tmp_path / ".env"
    _write_json(
        config_file,
        {
            "database": {
                "embedded_database": True,
                "host": "json-host",
                "database_name": "json-db",
            }
        },
    )
    env_file.write_text(
        "\n".join(
            (
                "EMBEDDED_DATABASE=false",
                "DATABASE_URL=postgresql://url-user:url-pass@url-host:6543/url-db",
                "DATABASE_USERNAME=env-user",
                "DATABASE_PASSWORD=env-pass",
                "DATABASE_PORT=7777",
                "DATABASE_SSL=true",
                "DATABASE_SSL_CA=/env/ca.pem",
                "DATABASE_CONNECT_TIMEOUT=55",
                "DATABASE_INSERT_BATCH_SIZE=2200",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    for key in (
        "EMBEDDED_DATABASE",
        "DATABASE_URL",
        "DATABASE_ENGINE",
        "DATABASE_HOST",
        "DATABASE_NAME",
        "DATABASE_USERNAME",
        "DATABASE_PASSWORD",
        "DATABASE_PORT",
        "DATABASE_SSL",
        "DATABASE_SSL_CA",
        "DATABASE_CONNECT_TIMEOUT",
        "DATABASE_INSERT_BATCH_SIZE",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        "server.configurations.environment.ENV_FILE_PATH", str(env_file)
    )
    reset_environment_bootstrap_for_tests()
    ensure_environment_loaded(force=True)

    manager = ConfigurationManager(config_path=config_file)
    manager.load()
    settings = manager.server_settings.database

    assert settings.embedded_database is False
    assert settings.engine == "postgresql+psycopg"
    assert settings.host == "url-host"
    assert settings.port == 7777
    assert settings.database_name == "url-db"
    assert settings.username == "env-user"
    assert settings.password == "env-pass"
    assert settings.ssl is True
    assert settings.ssl_ca == "/env/ca.pem"
    assert settings.connect_timeout == 55
    assert settings.insert_batch_size == 2200
