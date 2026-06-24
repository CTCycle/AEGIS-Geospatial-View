from __future__ import annotations

import json
import logging
from typing import Any

from server.domain.chat import ChatOperationResult
from server.domain.geographics import MapSession
from server.repositories.model_settings import ModelSettingsRepository
from server.services.llm.factory import LLMFactory
from server.services.llm.prompts import get_agent_response_prompt
from server.services.llm.types import LLMRequest

LOGGER = logging.getLogger(__name__)

###############################################################################
class GroundedResponseSynthesizer:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        settings_repo: ModelSettingsRepository | None = None,
        llm_factory: LLMFactory | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self.llm_factory = llm_factory or LLMFactory(settings_repo=self.settings_repo)
        self.enabled = (
            isinstance(self.settings_repo, ModelSettingsRepository)
            if enabled is None
            else enabled
        )

    # -------------------------------------------------------------------------
    def synthesize(
        self,
        *,
        user_text: str,
        fallback_text: str,
        operation: ChatOperationResult,
        map_session: MapSession | None = None,
        direct_result: dict[str, Any] | None = None,
        clarification_plan: dict[str, Any] | None = None,
        task_status: str | None = None,
    ) -> str:
        if operation.kind in {"error", "rejection"} or operation.status == "failed":
            return fallback_text
        if not self.enabled:
            return fallback_text
        settings = self.settings_repo.get_or_create()
        if not settings.agent_model_provider or not settings.agent_model_name:
            return fallback_text
        evidence = {
            "user_request": user_text,
            "verified_outcome": {
                "kind": operation.kind,
                "status": operation.status,
                "verified_summary": fallback_text,
                "warnings": list(operation.warnings),
            },
            "map": self._map_summary(map_session),
            "direct_result": self._bounded_value(direct_result),
            "clarification": self._bounded_value(clarification_plan),
            "task_status": task_status,
        }
        try:
            provider = self.llm_factory.get_chat_provider(
                settings.agent_model_provider
            )
            result = provider.chat(
                LLMRequest(
                    model=settings.agent_model_name,
                    temperature=0.35,
                    messages=[
                        {
                            "role": "system",
                            "content": get_agent_response_prompt(
                                provider=settings.agent_model_provider,
                                model=settings.agent_model_name,
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                "Write the final response using only this verified evidence:\n"
                                + json.dumps(
                                    evidence,
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                )
                            ),
                        },
                    ],
                    metadata={"purpose": "grounded_agent_response"},
                )
            )
        except Exception:
            LOGGER.warning("Grounded response synthesis failed", exc_info=True)
            return fallback_text
        return (result.content or "").strip() or fallback_text

    # -------------------------------------------------------------------------
    @staticmethod
    def _map_summary(map_session: MapSession | None) -> dict[str, Any] | None:
        if map_session is None:
            return None
        resolved = map_session.resolved_location
        return {
            "location": resolved.label if resolved is not None else None,
            "basemap": map_session.basemap_id,
            "overlays": [
                {
                    "id": overlay.get("id"),
                    "label": overlay.get("label") or overlay.get("name"),
                }
                for overlay in map_session.overlays
                if isinstance(overlay, dict)
            ],
            "warnings": list(map_session.compliance_warnings),
        }

    # -------------------------------------------------------------------------
    @classmethod
    def _bounded_value(cls, value: Any, *, depth: int = 0) -> Any:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return value[:1000]
        if depth >= 3:
            return None
        if isinstance(value, list):
            return [cls._bounded_value(item, depth=depth + 1) for item in value[:20]]
        if isinstance(value, dict):
            return {
                str(key)[:80]: cls._bounded_value(item, depth=depth + 1)
                for key, item in list(value.items())[:30]
            }
        return str(value)[:500]
