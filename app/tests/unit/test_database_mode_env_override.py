from __future__ import annotations

from server.common.constants import DATABASE_FILE_PATH
from server.configurations import build_database_settings


def test_database_settings_uses_constants_database_path() -> None:
    settings = build_database_settings({})
    assert settings.database_path == DATABASE_FILE_PATH
    assert settings.embedded_database is True


def test_database_settings_preserves_insert_batch_size() -> None:
    settings = build_database_settings({"insert_batch_size": 777})
    assert settings.insert_batch_size == 777


def test_database_settings_reads_external_database_keys_from_json() -> None:
    settings = build_database_settings(
        {
            "embedded_database": False,
            "engine": "postgresql+psycopg",
            "host": "json-host",
            "port": 6432,
            "database_name": "json-db",
            "username": "json-user",
            "password": "json-pass",
            "ssl": True,
            "ssl_ca": "/json/ca.pem",
            "connect_timeout": 45,
            "insert_batch_size": 1500,
        }
    )

    assert settings.embedded_database is False
    assert settings.engine == "postgresql+psycopg"
    assert settings.host == "json-host"
    assert settings.port == 6432
    assert settings.database_name == "json-db"
    assert settings.username == "json-user"
    assert settings.password == "json-pass"
    assert settings.ssl is True
    assert settings.ssl_ca == "/json/ca.pem"
    assert settings.connect_timeout == 45
    assert settings.insert_batch_size == 1500
