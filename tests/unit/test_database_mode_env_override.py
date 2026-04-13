from __future__ import annotations

from AEGIS.server.configurations import build_database_settings


def test_db_settings_use_json_payload_for_embedded_mode() -> None:
    payload = {
        "embedded_database": True,
        "engine": "postgres",
        "host": "json-host",
        "port": 5432,
        "database_name": "json-db",
        "username": "json-user",
        "password": "json-pass",
        "ssl": True,
        "ssl_ca": "/json/ca.pem",
        "connect_timeout": 20,
        "insert_batch_size": 777,
    }

    settings = build_database_settings(payload)

    assert settings.embedded_database is True
    assert settings.engine is None
    assert settings.host is None
    assert settings.port is None
    assert settings.database_name is None
    assert settings.username is None
    assert settings.password is None
    assert settings.ssl is False
    assert settings.ssl_ca is None
    assert settings.connect_timeout == 10
    assert settings.insert_batch_size == 777


def test_external_db_settings_use_json_payload_and_ignore_db_env(monkeypatch) -> None:
    payload = {
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

    monkeypatch.setenv("DB_EMBEDDED", "true")
    monkeypatch.setenv("DB_ENGINE", "sqlite")
    monkeypatch.setenv("DB_HOST", "env-db.example.internal")
    monkeypatch.setenv("DB_PORT", "5555")
    monkeypatch.setenv("DB_NAME", "env-db")
    monkeypatch.setenv("DB_USER", "env-user")
    monkeypatch.setenv("DB_PASSWORD", "env-pass")
    monkeypatch.setenv("DB_SSL", "false")
    monkeypatch.setenv("DB_SSL_CA", "/etc/ssl/certs/ca.pem")
    monkeypatch.setenv("DB_CONNECT_TIMEOUT", "11")
    monkeypatch.setenv("DB_INSERT_BATCH_SIZE", "200")

    settings = build_database_settings(payload)

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
