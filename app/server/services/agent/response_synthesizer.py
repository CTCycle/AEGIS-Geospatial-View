from __future__ import annotations

from server.common.typing import is_json_array, is_json_object

import logging
import re
from contextvars import ContextVar
from time import monotonic
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from server.contracts.chat import ChatOperationResult
from server.contracts.geospatial import MapSession
from server.repositories.model_settings import ModelSettingsRepository
from server.services.llm.factory import LLMFactory
from server.prompts.response import build_response_prompt
from server.services.llm.errors import LLMProviderRequestError, LLMStructuredOutputError
from server.services.llm.context_profile_resolver import ModelContextProfileResolver
from server.services.llm.request_deadline import REQUEST_DEADLINE_METADATA_KEY
from server.services.llm.types import LLMRequest

LOGGER = logging.getLogger(__name__)


###############################################################################
class GroundedSynthesisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)
    used_evidence_keys: list[
        Literal[
            "user_request",
            "verified_outcome",
            "map",
            "direct_result",
            "clarification",
            "task_status",
            "active_conversation_instructions",
            "task_snapshot",
        ]
    ] = Field(min_length=1, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=20)


###############################################################################
class GroundedResponseSynthesizer:
    SYNTHESIS_TIMEOUT_SECONDS = 35.0
    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        settings_repo: ModelSettingsRepository,
        llm_factory: LLMFactory,
        context_profile_resolver: ModelContextProfileResolver | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.settings_repo = settings_repo
        self.llm_factory = llm_factory
        self.context_profile_resolver = context_profile_resolver
        self.enabled = True if enabled is None else enabled
        self._last_context_usage: ContextVar[dict[str, Any] | None] = ContextVar(
            "aegis_synthesis_context_usage", default=None
        )
        self._last_failure_category: ContextVar[str | None] = ContextVar(
            "aegis_synthesis_failure_category", default=None
        )
        self._last_failure_detail: ContextVar[str | None] = ContextVar(
            "aegis_synthesis_failure_detail", default=None
        )

    # -------------------------------------------------------------------------
    @property
    def last_context_usage(self) -> dict[str, Any] | None:
        return self._last_context_usage.get()

    # -------------------------------------------------------------------------
    @last_context_usage.setter
    def last_context_usage(self, value: dict[str, Any] | None) -> None:
        self._last_context_usage.set(value)

    # -------------------------------------------------------------------------
    @property
    def last_failure_category(self) -> str | None:
        return self._last_failure_category.get()

    # -------------------------------------------------------------------------
    @last_failure_category.setter
    def last_failure_category(self, value: str | None) -> None:
        self._last_failure_category.set(value)

    # -------------------------------------------------------------------------
    @property
    def last_failure_detail(self) -> str | None:
        return self._last_failure_detail.get()

    # -------------------------------------------------------------------------
    @last_failure_detail.setter
    def last_failure_detail(self, value: str | None) -> None:
        self._last_failure_detail.set(value)

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
        settings = self.settings_repo.get_required()
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
            provider = self.llm_factory.get_provider(settings.agent_model_provider)
            request = LLMRequest(
                model=settings.agent_model_name,
                temperature=0.35,
                messages=build_response_prompt(evidence),
                metadata={
                    **(
                        self.context_profile_resolver.request_metadata(
                            settings.agent_model_provider,
                            settings.agent_model_name,
                        )
                        if self.context_profile_resolver is not None
                        else {}
                    ),
                    "max_tokens": 4096,
                    "purpose": "grounded_agent_response",
                    REQUEST_DEADLINE_METADATA_KEY: (
                        monotonic() + self.SYNTHESIS_TIMEOUT_SECONDS
                    ),
                },
            )
            payload = provider.structured_output(
                request,
                GroundedSynthesisResult,
            )
            usage = getattr(payload, "context_usage", None)
            self.last_context_usage = dict(usage) if is_json_object(usage) else None
            result = GroundedSynthesisResult.model_validate(payload)
            if any(key not in evidence for key in result.used_evidence_keys):
                raise ValueError(
                    "Synthesis referenced evidence keys outside the verified payload."
                )
            if not self._content_matches_verified_state(
                result.content,
                operation=operation,
                map_session=map_session,
            ):
                raise ValueError("Synthesis contradicted the verified operation state.")
        except LLMStructuredOutputError as exc:
            self.last_failure_category = exc.category
            self.last_failure_detail = exc.detail
            LOGGER.warning(
                "Grounded response synthesis failed category=%s",
                exc.category,
                exc_info=True,
            )
            return fallback_text
        except LLMProviderRequestError as exc:
            self.last_failure_category = exc.category
            self.last_failure_detail = f"Provider request failed with code {exc.code}."
            LOGGER.warning(
                "Grounded response synthesis failed category=%s",
                exc.category,
                exc_info=True,
            )
            return fallback_text
        except Exception:
            self.last_failure_category = "response_parsing"
            self.last_failure_detail = (
                "The grounded response did not match verified evidence."
            )
            LOGGER.warning(
                "Grounded response synthesis failed category=response_parsing",
                exc_info=True,
            )
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
        if (
            operation.status != "success"
            or not map_session
            or not map_session.overlay_collection.instances
        ):
            return True
        if map_session.compliance_warnings:
            return True
        normalized = re.sub(r"\s+", " ", content.casefold())
        if re.search(
            r"\b(?:failed|failure|error|not available|could not|unable to)\b",
            normalized,
        ):
            return False
        if GroundedResponseSynthesizer._feature_count(map_session) <= 0:
            return True
        contradiction_patterns = (
            r"\b(?:no|without)\s+(?:direct\s+)?(?:result|results|feature|features|data|points|records|locations|sites)\b",
            r"\b(?:does not|doesn't|did not|didn't)\s+(?:include|contain|show|provide|return)\b.{0,80}\b(?:result|results|feature|features|data|points|records|locations|sites)\b",
            r"(?<!no )(?<!not )\b(?:further|additional|another)\s+(?:search|query|lookup|request)\b\s+(?:is\s+)?(?:needed|required|necessary)\b",
            r"\b(?:pending|still pending|not completed|in progress)\b",
        )
        return not any(
            re.search(pattern, normalized) for pattern in contradiction_patterns
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
                GroundedResponseSynthesizer._overlay_summary(
                    {
                        **instance.descriptor,
                        "id": instance.instance_id,
                        "capability_id": instance.capability_id,
                        "label": instance.label,
                        "provider": instance.provider,
                        "type": instance.overlay_type,
                        "rendering_mode": instance.rendering_mode,
                        "visible": instance.visible,
                        "default_opacity": instance.opacity,
                        "inspections": [
                            inspection.model_dump(mode="json")
                            for inspection in instance.inspections
                        ],
                    }
                )
                for instance in map_session.overlay_collection.instances
            ],
            "warnings": list(map_session.compliance_warnings),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _overlay_summary(overlay: dict[str, Any]) -> dict[str, Any]:
        rendering_mode = overlay.get("rendering_mode")
        metadata_only = rendering_mode == "metadata-only"
        summary = {
            "id": overlay.get("id"),
            "label": overlay.get("label") or overlay.get("name"),
            "rendering_mode": rendering_mode,
            "source_protocol": overlay.get("source_protocol"),
            "rendered": not metadata_only,
            "status": "metadata_only" if metadata_only else "rendered",
        }
        data = overlay.get("data")
        if is_json_object(data) and data.get("type") == "FeatureCollection":
            features = data.get("features")
            if is_json_array(features):
                summary["feature_count"] = len(features)
                categories = sorted(
                    {
                        str(properties[key]).strip()
                        for feature in features[:100]
                        if is_json_object(feature)
                        and is_json_object(properties := feature.get("properties"))
                        for key in ("category", "amenity", "kind")
                        if isinstance(properties.get(key), str)
                        and properties[key].strip()
                    }
                )
                if categories:
                    summary["categories"] = categories[:20]
        for key in (
            "provider",
            "source_url",
            "fetched_at",
            "observation_time",
            "result_status",
            "result_type",
            "coverage",
            "spatial_resolution",
            "units",
            "partial",
            "total_results",
            "returned_results",
            "limit",
            "truncated",
            "radius_m",
        ):
            if overlay.get(key) is not None:
                summary[key] = GroundedResponseSynthesizer._bounded_value(
                    overlay[key]
                )
        return summary

    # -------------------------------------------------------------------------
    @staticmethod
    def _feature_count(map_session: MapSession) -> int:
        count = 0
        for instance in map_session.overlay_collection.instances:
            data = instance.descriptor.get("data")
            if not is_json_object(data) or data.get("type") != "FeatureCollection":
                continue
            features = data.get("features")
            if is_json_array(features):
                count += len(features)
        return count

    # -------------------------------------------------------------------------
    @classmethod
    def _bounded_value(cls, value: Any, *, depth: int = 0) -> Any:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return value[:1000]
        # Provider results commonly have an execution envelope, a tool
        # wrapper, and a provider result wrapper before reaching measurements.
        # Keep enough depth for those values to reach the grounded model while
        # retaining strict size bounds for arbitrary provider payloads.
        if depth >= 5:
            return None
        if is_json_array(value):
            return [cls._bounded_value(item, depth=depth + 1) for item in value[:20]]
        if is_json_object(value):
            return {
                str(key)[:80]: cls._bounded_value(item, depth=depth + 1)
                for key, item in list(value.items())[:30]
            }
        return str(value)[:500]
