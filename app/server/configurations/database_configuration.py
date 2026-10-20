from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from server.common.constants import DEFAULT_SQLITE_LOCK_TIMEOUT_SECONDS
from server.common.paths import (
    resolve_database_configuration_path,
    resolve_database_file_path,
    resolve_runtime_data_root,
)


class DatabaseConfigurationError(RuntimeError):
    """Raised when the independent database configuration cannot be loaded."""


class DatabaseConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    backend: Literal["sqlite"] = "sqlite"
    database_path: str = Field(min_length=1)
    sqlite_lock_timeout_seconds: int = Field(
        default=DEFAULT_SQLITE_LOCK_TIMEOUT_SECONDS, ge=1
    )

    @field_validator("database_path")
    @classmethod
    def normalize_database_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("database_path must not be blank")
        candidate = Path(normalized).expanduser()
        if not candidate.is_absolute():
            candidate = resolve_runtime_data_root() / candidate
        return str(candidate.resolve())


def load_database_configuration() -> DatabaseConfiguration:
    """Load or create the database-only configuration outside the database."""

    path = resolve_database_configuration_path()
    backup_path = _backup_path(path)
    if path.is_file():
        try:
            configuration = _read_configuration(path)
        except DatabaseConfigurationError as primary_error:
            if not backup_path.is_file():
                raise primary_error
            try:
                configuration = _read_configuration(backup_path)
            except DatabaseConfigurationError as backup_error:
                raise DatabaseConfigurationError(
                    "The database configuration and its recovery copy are invalid. "
                    "Preserve both files and correct the configuration before starting AEGIS."
                ) from backup_error
            _write_primary(path, configuration)
    elif backup_path.is_file():
        configuration = _read_configuration(backup_path)
        _write_primary(path, configuration)
    else:
        configuration = DatabaseConfiguration(
            database_path=str(resolve_database_file_path())
        )
        _write_primary(path, configuration)

    return configuration


def save_database_configuration(
    configuration: DatabaseConfiguration,
) -> DatabaseConfiguration:
    """Atomically replace the selected configuration, keeping one recovery copy."""

    validated = DatabaseConfiguration.model_validate(configuration.model_dump())
    path = resolve_database_configuration_path()
    if path.is_file():
        current = _read_configuration(path)
        _write_backup(_backup_path(path), current)
    _write_primary(path, validated)
    return validated


def restore_database_configuration(
    configuration: DatabaseConfiguration,
) -> DatabaseConfiguration:
    """Restore the active record without replacing the last-known-good backup."""

    validated = DatabaseConfiguration.model_validate(configuration.model_dump())
    _write_primary(resolve_database_configuration_path(), validated)
    return validated


def _read_configuration(path: Path) -> DatabaseConfiguration:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return DatabaseConfiguration.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise DatabaseConfigurationError(
            f"Database configuration at {path} is invalid."
        ) from exc


def _backup_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.bak")


def _write_backup(destination: Path, configuration: DatabaseConfiguration) -> None:
    _atomic_write(destination, configuration)


def _write_primary(path: Path, configuration: DatabaseConfiguration) -> None:
    _atomic_write(path, configuration)


def _atomic_write(path: Path, configuration: DatabaseConfiguration) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(configuration.model_dump(mode="json"), stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
