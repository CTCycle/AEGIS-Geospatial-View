from __future__ import annotations

from AEGIS.server.configurations.server import build_database_settings


def test_db_embedded_env_override_takes_precedence(monkeypatch) -> None:
    payload = {
        "embedded_database": False,
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

    monkeypatch.setenv("DB_EMBEDDED", "true")

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


def test_external_db_env_fields_applied_when_embedded_disabled(monkeypatch) -> None:
    payload = {
        "embedded_database": True,
        "engine": "sqlite",
        "host": "json-host",
        "port": 5432,
        "database_name": "json-db",
        "username": "json-user",
        "password": "json-pass",
        "ssl": False,
        "ssl_ca": None,
        "connect_timeout": 10,
        "insert_batch_size": 1000,
    }

    monkeypatch.setenv("DB_EMBEDDED", "false")
    monkeypatch.setenv("DB_ENGINE", "postgresql+psycopg")
    monkeypatch.setenv("DB_HOST", "env-db.example.internal")
    monkeypatch.setenv("DB_PORT", "6432")
    monkeypatch.setenv("DB_NAME", "env-db")
    monkeypatch.setenv("DB_USER", "env-user")
    monkeypatch.setenv("DB_PASSWORD", "env-pass")
    monkeypatch.setenv("DB_SSL", "true")
    monkeypatch.setenv("DB_SSL_CA", "/etc/ssl/certs/ca.pem")
    monkeypatch.setenv("DB_CONNECT_TIMEOUT", "45")
    monkeypatch.setenv("DB_INSERT_BATCH_SIZE", "1500")

    settings = build_database_settings(payload)

    assert settings.embedded_database is False
    assert settings.engine == "postgresql+psycopg"
    assert settings.host == "env-db.example.internal"
    assert settings.port == 6432
    assert settings.database_name == "env-db"
    assert settings.username == "env-user"
    assert settings.password == "env-pass"
    assert settings.ssl is True
    assert settings.ssl_ca == "/etc/ssl/certs/ca.pem"
    assert settings.connect_timeout == 45
    assert settings.insert_batch_size == 1500
