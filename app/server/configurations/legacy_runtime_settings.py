from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from server.common.paths import ROOT_DIR
from server.configurations.settings import AppSettings, RUNTIME_SETTING_BLOCKS


LEGACY_RUNTIME_SETTINGS_PATH = ROOT_DIR / "settings" / "configurations.json"
LEGACY_REQUIRED_BLOCKS = tuple(
    block for block in RUNTIME_SETTING_BLOCKS if block != "agent_execution"
)


class LegacyRuntimeSettingsError(RuntimeError):
    """Raised when the legacy runtime settings cannot be imported safely."""


def legacy_runtime_settings_path() -> Path:
    return LEGACY_RUNTIME_SETTINGS_PATH


def load_legacy_runtime_settings(path: Path | None = None) -> AppSettings | None:
    source = Path(path or LEGACY_RUNTIME_SETTINGS_PATH)
    if not source.exists():
        return None
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyRuntimeSettingsError(
            f"Unable to load legacy runtime settings from {source}."
        ) from exc
    if not isinstance(raw, dict):
        raise LegacyRuntimeSettingsError(
            "Legacy runtime settings must be a JSON object."
        )
    typed_raw = cast(dict[str, Any], raw)

    unknown = sorted(set(typed_raw) - set(RUNTIME_SETTING_BLOCKS))
    if unknown:
        raise LegacyRuntimeSettingsError(
            "Unsupported legacy runtime settings blocks: " + ", ".join(unknown)
        )
    missing = [block for block in LEGACY_REQUIRED_BLOCKS if block not in typed_raw]
    if missing:
        raise LegacyRuntimeSettingsError(
            "Missing legacy runtime settings blocks: " + ", ".join(missing)
        )
    try:
        return AppSettings.model_validate(typed_raw)
    except ValidationError as exc:
        raise LegacyRuntimeSettingsError(
            f"Invalid legacy runtime settings in {source}: {exc}"
        ) from exc


def retire_legacy_runtime_settings(path: Path | None = None) -> None:
    source = Path(path or LEGACY_RUNTIME_SETTINGS_PATH)
    if not source.exists():
        return
    try:
        source.unlink()
    except OSError as exc:
        raise LegacyRuntimeSettingsError(
            f"Runtime settings were persisted, but the legacy file could not be retired: {source}."
        ) from exc
