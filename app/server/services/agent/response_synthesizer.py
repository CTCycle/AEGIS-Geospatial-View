from __future__ import annotations

from server.common.typing import is_json_array, is_json_object

import json
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.contracts.chat import ChatOperationResult
from server.contracts.geospatial import MapSession
from server.repositories.model_settings import ModelSettingsRepository
from server.services.llm.factory import LLMFactory
from server.services.llm.prompts import get_agent_response_prompt
from server.services.llm.errors import LLMProviderRequestError, LLMStructuredOutputError
from server.services.llm.types import LLMRequest

LOGGER = logging.getLogger(__name__)

###############################################################################
class GroundedSynthesisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)
    used_evidence_keys: list[Literal[
        "user_request",
        "verified_outcome",
        "map",
        "direct_result",
        "clarification",
        "task_status",
        "active_conversation_instructions",
        "task_snapshot",
    ]] = Field(min_length=1, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=20)

###############################################################################
class GroundedResponseSynthesizer:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        settings_repo: ModelSettingsRepository,
        llm_factory: LLMFactory,
        enabled: bool | None = None,
    ) -> None:
        self.settings_repo = settings_repo
        self.llm_factory = llm_factory
        self.enabled = True if enabled is None else enabled
        self.last_context_usage: dict[str, Any] | None = None
        self.last_failure_category: str | None = None
        self.last_failure_detail: str | None = None

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
        active_instructions: list[dict[str, Any]] | None = None,
        task_snapshot: dict[str, Any] | None = None,
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
            "active_conversation_instructions": active_instructions or [],
            "task_snapshot": self._bounded_value(task_snapshot),
        }
        self.last_context_usage = None
        self.last_failure_category = None
        self.last_failure_detail = None
        try:
            provider = self.llm_factory.get_provider(
                settings.agent_model_provider
            )
            payload = provider.structured_output(
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
                ),
                GroundedSynthesisResult,
            )
            result = GroundedSynthesisResult.model_validate(payload)
            usage = getattr(provider, "last_context_usage", None)
            self.last_context_usage = dict(usage) if is_json_object(usage) else None
            if any(key not in evidence for key in result.used_evidence_keys):
                raise ValueError("Synthesis referenced evidence keys outside the verified payload.")
            if not self._content_matches_verified_state(
                result.content,
                operation=operation,
                map_session=map_session,
            ):
                raise ValueError("Synthesis contradicted the verified operation state.")
        except LLMStructuredOutputError as exc:
            self.last_failure_category = exc.category
            self.last_failure_detail = exc.detail
            LOGGER.warning("Grounded response synthesis failed category=%s", exc.category, exc_info=True)
            return fallback_text
        except LLMProviderRequestError as exc:
            self.last_failure_category = exc.category
            self.last_failure_detail = f"Provider request failed with code {exc.code}."
            LOGGER.warning("Grounded response synthesis failed category=%s", exc.category, exc_info=True)
            return fallback_text
        except Exception as exc:
            self.last_failure_category = "response_parsing"
            self.last_failure_detail = "The grounded response did not match verified evidence."
            LOGGER.warning("Grounded response synthesis failed category=response_parsing", exc_info=True)
            return fallback_text
        return result.content.strip() or fallback_text

    # -------------------------------------------------------------------------
    @staticmethod
    def _content_matches_verified_state(
        content: str,
        *,
        operation: ChatOperationResult,
        map_session: MapSession | None,
    ) -> bool:
        """Reject obvious model claims that contradict a successful payload."""
        if operation.status != "success" or not map_session or not map_session.overlays:
            return True
        if map_session.compliance_warnings:
            return True
        normalized = re.sub(r"\s+", " ", content.casefold())
        return not bool(
            re.search(
                r"\b(?:failed|failure|error|not available|could not|unable to)\b",
                normalized,
            )
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _map_summary(map_session: MapSession | None) -> dict[str, Any] | None:
        if map_session is None:
            return None
        resolved = map_session.resolved_location
        return {
            "location": resolved.label,
            "basemap": map_session.basemap_id,
            "overlays": [
                {
                    "id": overlay.get("id"),
                    "label": overlay.get("label") or overlay.get("name"),
                    "rendering_mode": overlay.get("rendering_mode"),
                    "source_protocol": overlay.get("source_protocol"),
                    "display_limitation": (
                        "metadata/setup context only; do not describe as live rendered map data"
                        if overlay.get("rendering_mode") == "metadata-only"
                        else None
                    ),
                }
                for overlay in map_session.overlays
                if is_json_object(overlay)
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
        if is_json_array(value):
            return [cls._bounded_value(item, depth=depth + 1) for item in value[:20]]
        if is_json_object(value):
            return {
                str(key)[:80]: cls._bounded_value(item, depth=depth + 1)
                for key, item in list(value.items())[:30]
            }
        return str(value)[:500]
