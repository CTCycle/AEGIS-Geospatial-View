from __future__ import annotations

from typing import Any, Mapping

from server.configurations.settings import AppSettings
from server.contracts.settings import RuntimeSettingsResponse
from server.repositories.runtime_settings import (
    RUNTIME_SETTINGS_SCHEMA_VERSION,
    RuntimeSettingsRepository,
)


class RuntimeSettingsService:
    """Application-facing service for typed runtime settings updates."""

    def __init__(self, repository: RuntimeSettingsRepository) -> None:
        self.repository = repository

    def get_settings(self) -> RuntimeSettingsResponse:
        return self._response(self.repository.get_required())

    def update_settings(
        self, patch: Mapping[str, Any]
    ) -> RuntimeSettingsResponse:
        updated = self.repository.update(patch)
        restart_required = any(key != "agent_execution" and bool(value) for key, value in patch.items())
        return self._response(
            updated,
            restart_required=restart_required,
            message=(
                "Settings saved. Restart AEGIS to apply runtime changes."
                if restart_required
                else "Agent settings saved. New runs use these values; active runs retain their original limits."
                if patch.get("agent_execution")
                else None
            ),
        )

    @staticmethod
    def _response(
        settings: AppSettings,
        *,
        restart_required: bool = False,
        message: str | None = None,
    ) -> RuntimeSettingsResponse:
        return RuntimeSettingsResponse.model_validate(
            {
                "schema_version": RUNTIME_SETTINGS_SCHEMA_VERSION,
                **settings.runtime_payload(),
                "restart_required": restart_required,
                "message": message,
            }
        )
