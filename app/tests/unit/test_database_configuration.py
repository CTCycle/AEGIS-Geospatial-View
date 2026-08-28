from __future__ import annotations

from pathlib import Path

import pytest

from server.common.paths import DATABASE_FILE_PATH
from server.configurations import build_database_settings

###############################################################################
def test_database_settings_use_default_sqlite_path(monkeypatch) -> None:
    monkeypatch.delenv("AEGIS_DATA_DIR", raising=False)
    monkeypatch.delenv("SQLITE_LOCK_TIMEOUT", raising=False)

    settings = build_database_settings()

    assert settings.database_path == str(DATABASE_FILE_PATH)
    assert settings.sqlite_lock_timeout_seconds == 60

###############################################################################
def test_database_settings_use_short_data_directory_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))

    settings = build_database_settings()

    assert settings.database_path == str(tmp_path / "database.db")

###############################################################################
def test_database_settings_read_sqlite_lock_timeout(monkeypatch) -> None:
    monkeypatch.setenv("SQLITE_LOCK_TIMEOUT", "12")

    assert build_database_settings().sqlite_lock_timeout_seconds == 12

###############################################################################
@pytest.mark.parametrize("value", ["0", "-1", "not-an-integer"])
def test_database_settings_reject_invalid_sqlite_lock_timeout(
    monkeypatch,
    value: str,
) -> None:
    monkeypatch.setenv("SQLITE_LOCK_TIMEOUT", value)

    with pytest.raises(RuntimeError, match="SQLITE_LOCK_TIMEOUT"):
        build_database_settings()

