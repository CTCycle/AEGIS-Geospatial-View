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
        self._startup_payload = repository.get_required().runtime_payload()

    def get_settings(self) -> RuntimeSettingsResponse:
        settings = self.repository.get_required()
        restart_required = self._restart_required(settings)
        return self._response(
            settings,
            restart_required=restart_required,
            message=(
                "Settings saved. Restart AEGIS to apply runtime changes."
                if restart_required
                else None
            ),
        )

    def update_settings(
        self, patch: Mapping[str, Any]
    ) -> RuntimeSettingsResponse:
        updated = self.repository.update(patch)
        restart_required = self._restart_required(updated)
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

    def _restart_required(self, settings: AppSettings) -> bool:
        current_payload = settings.runtime_payload()
        return any(
            block != "agent_execution" and current_payload[block] != startup_value
            for block, startup_value in self._startup_payload.items()
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
