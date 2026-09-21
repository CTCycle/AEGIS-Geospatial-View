from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, cast

from pydantic import ValidationError
from server.common.time import utc_now_naive
from server.configurations.legacy_runtime_settings import (
    LegacyRuntimeSettingsError,
    legacy_runtime_settings_path,
    load_legacy_runtime_settings,
    retire_legacy_runtime_settings,
)
from server.configurations.settings import AppSettings, RUNTIME_SETTING_BLOCKS
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas.models import ApplicationRuntimeSettingsRecord


RUNTIME_SETTINGS_SCHEMA_VERSION = 1


class RuntimeSettingsRepository:
    """Typed persistence boundary for application-editable runtime settings."""

    def __init__(self, database: SQLiteRepository) -> None:
        self._session_factory = database.session

    def get(self) -> AppSettings | None:
        with self._session_factory() as session:
            record = session.get(ApplicationRuntimeSettingsRecord, 1)
            if record is None:
                return None
            return self._validate_record(record)

    def get_required(self) -> AppSettings:
        settings = self.get()
        if settings is None:
            raise RuntimeError(
                "The application runtime settings record is missing; database initialization must seed it."
            )
        return settings

    def initialize_defaults(self, *, legacy_path: Path | None = None) -> AppSettings:
        existing = self.get()
        if existing is not None:
            return existing

        source = Path(legacy_path or legacy_runtime_settings_path())
        imported = load_legacy_runtime_settings(source)
        settings = imported or AppSettings()
        payload = self._validated_payload(settings.runtime_payload())

        with self._session_factory() as session:
            existing_record = session.get(ApplicationRuntimeSettingsRecord, 1)
            if existing_record is not None:
                return self._validate_record(existing_record)
            session.add(
                ApplicationRuntimeSettingsRecord(
                    id=1,
                    schema_version=RUNTIME_SETTINGS_SCHEMA_VERSION,
                    payload_json=payload,
                )
            )
            session.commit()

        if imported is not None:
            try:
                retire_legacy_runtime_settings(source)
            except LegacyRuntimeSettingsError:
                # The committed SQLite row is authoritative.  Keep startup
                # successful if a locked or read-only legacy file cannot be
                # removed; the next maintenance run can retire it safely.
                pass
        return self.get_required()

    def seed_required(self, *, legacy_path: Path | None = None) -> AppSettings:
        return self.initialize_defaults(legacy_path=legacy_path)

    def replace(self, settings: AppSettings | Mapping[str, Any]) -> AppSettings:
        candidate = self._coerce_settings(settings)
        payload = self._validated_payload(candidate.runtime_payload())
        with self._session_factory() as session:
            record = session.get(ApplicationRuntimeSettingsRecord, 1)
            if record is None:
                raise RuntimeError(
                    "The application runtime settings record is missing; database initialization must seed it."
                )
            record.schema_version = RUNTIME_SETTINGS_SCHEMA_VERSION
            record.payload_json = payload
            record.updated_at = utc_now_naive()
            session.commit()
        return self.get_required()

    def update(self, patch: Mapping[str, Any]) -> AppSettings:
        current = self.get_required()
        merged = deepcopy(current.runtime_payload())
        unknown = sorted(set(patch.keys()) - set(RUNTIME_SETTING_BLOCKS))
        if unknown:
            raise ValueError(
                "Unsupported runtime settings blocks: " + ", ".join(unknown)
            )
        for block, value in patch.items():
            if not isinstance(value, Mapping):
                raise ValueError(f"Runtime settings block '{block}' must be an object.")
            block_payload = merged[block]
            if not isinstance(block_payload, dict):
                raise ValueError(f"Runtime settings block '{block}' must be an object.")
            typed_block_payload = cast(dict[str, Any], block_payload)
            nested: dict[str, Any] = dict(cast(Mapping[str, Any], value))
            unknown_fields = sorted(set(nested.keys()) - set(typed_block_payload.keys()))
            if unknown_fields:
                raise ValueError(
                    f"Unsupported runtime settings in {block}: "
                    + ", ".join(unknown_fields)
                )
            typed_block_payload.update(nested)
        return self.replace(merged)

    @staticmethod
    def _coerce_settings(settings: AppSettings | Mapping[str, Any]) -> AppSettings:
        if isinstance(settings, AppSettings):
            return settings
        try:
            return AppSettings.model_validate(settings)
        except ValidationError as exc:
            raise ValueError(f"Invalid application runtime settings: {exc}") from exc

    @staticmethod
    def _validated_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        missing = sorted(set(RUNTIME_SETTING_BLOCKS) - set(payload.keys()))
        unknown = sorted(set(payload.keys()) - set(RUNTIME_SETTING_BLOCKS))
        if missing:
            raise ValueError(
                "Missing runtime settings blocks: " + ", ".join(missing)
            )
        if unknown:
            raise ValueError(
                "Unsupported runtime settings blocks: " + ", ".join(unknown)
            )
        try:
            settings = AppSettings.model_validate(dict(payload))
        except ValidationError as exc:
            raise ValueError(f"Invalid application runtime settings: {exc}") from exc
        return settings.runtime_payload()

    def _validate_record(self, record: ApplicationRuntimeSettingsRecord) -> AppSettings:
        if record.schema_version != RUNTIME_SETTINGS_SCHEMA_VERSION:
            raise RuntimeError(
                f"Unsupported application runtime settings schema version {record.schema_version}."
            )
        try:
            payload = self._validated_payload(record.payload_json)
        except ValueError as exc:
            raise RuntimeError(
                "Persisted application runtime settings are invalid; refusing to fall back to defaults."
            ) from exc
        try:
            return AppSettings.model_validate(payload)
        except ValidationError as exc:
            raise RuntimeError(
                "Persisted application runtime settings are invalid."
            ) from exc
