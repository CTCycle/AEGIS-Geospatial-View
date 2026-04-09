from __future__ import annotations

import json
import re

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.prompts import AGENT_DECISION_SYSTEM_PROMPT
from AEGIS.server.services.llm.types import ChatCompletionRequest

###############################################################################
class DecisionService:
    GEOCODE_PATTERNS = (
        re.compile(r"\b(coordinates?|latitude|longitude|lat\s*/\s*lon|lat[- ]?lon)\b", re.IGNORECASE),
        re.compile(r"\b(where is\b|\bgeocode\b|\blocat(?:e|ion of)\b)", re.IGNORECASE),
    )
    AMBIGUOUS_REQUEST_PATTERNS = (
        re.compile(r"\b(best|ideal|optimum|optimize|most suitable)\b", re.IGNORECASE),
    )
    GEOSPATIAL_KEYWORDS = {
        "map",
        "layer",
        "layers",
        "overlay",
        "overlays",
        "basemap",
        "satellite",
        "imagery",
        "traffic",
        "weather",
        "air",
        "quality",
        "fire",
        "fires",
        "smoke",
        "ozone",
        "precipitation",
        "temperature",
        "terrain",
        "solar",
        "noise",
        "cover",
        "geospatial",
        "geographic",
        "coordinates",
        "latitude",
        "longitude",
    }

    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

    def _is_geocode_request(self, user_message: str) -> bool:
        normalized = user_message.strip()
        return any(pattern.search(normalized) for pattern in self.GEOCODE_PATTERNS)

    def _looks_like_geospatial_request(self, user_message: str, extracted_state: ExtractedIntent) -> bool:
        haystack = " ".join(
            [
                user_message,
                extracted_state.user_goal,
                " ".join(extracted_state.filters),
                extracted_state.base_map_type or "",
            ]
        ).lower()
        return any(keyword in haystack for keyword in self.GEOSPATIAL_KEYWORDS)

    def _unsupported_request_decision(self) -> AgentDecision:
        return AgentDecision(
            decision="clarify",
            execution_mode="clarify",
            tool_target=None,
            should_trigger_search=False,
            location_status="missing",
            requires_geocoding=False,
            clarification_question=None,
            reasoning_summary="Unsupported non-geospatial request",
            feasibility={
                "is_supported": False,
                "blocking_reason": (
                    "I can help with location-based geospatial requests and coordinate lookup."
                ),
            },
        )

    def _ambiguous_request_decision(self) -> AgentDecision:
        return AgentDecision(
            decision="clarify",
            execution_mode="clarify",
            tool_target=None,
            should_trigger_search=False,
            location_status="partial",
            requires_geocoding=False,
            clarification_question=(
                "Which exact location or area should I focus on, and what geospatial factor matters most?"
            ),
            reasoning_summary="Ambiguous geospatial goal",
        )

    # -------------------------------------------------------------------------
    def decide(
        self,
        *,
        conversation_context: str,
        user_message: str,
        extracted_state: ExtractedIntent,
        retrieval: dict[str, list[dict[str, object]]],
    ) -> AgentDecision:
        # Deterministic guardrails first.
        has_coordinates = (
            extracted_state.coordinates.latitude is not None
            and extracted_state.coordinates.longitude is not None
        )
        has_text_location = any(
            [
                extracted_state.location.address,
                extracted_state.location.city,
                extracted_state.location.country,
            ]
        )
        is_geocode_request = self._is_geocode_request(user_message)
        is_geospatial_request = self._looks_like_geospatial_request(user_message, extracted_state)
        if not is_geocode_request and not is_geospatial_request:
            return self._unsupported_request_decision()
        if any(pattern.search(user_message) for pattern in self.AMBIGUOUS_REQUEST_PATTERNS):
            return self._ambiguous_request_decision()
        if not has_coordinates and not has_text_location:
            return AgentDecision(
                decision="clarify",
                execution_mode="clarify",
                tool_target=None,
                should_trigger_search=False,
                location_status="missing",
                requires_geocoding=False,
                clarification_question="Which location should I search on the map?",
                reasoning_summary="Missing location",
            )
        if is_geocode_request:
            return AgentDecision(
                decision="search_and_complete",
                execution_mode="geocode",
                tool_target="location_to_coordinates",
                should_trigger_search=False,
                location_status="valid" if has_text_location else "partial",
                requires_geocoding=has_text_location and not has_coordinates,
                clarification_question=None,
                reasoning_summary="Direct coordinate lookup request",
            )

        try:
            provider = self.llm_factory.get_agent_provider(self.provider)
            request = ChatCompletionRequest(
                model=self.model,
                messages=[
                    {"role": "system", "content": AGENT_DECISION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": conversation_context,
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "user_message": user_message,
                                "extracted_state": extracted_state.model_dump(mode="json"),
                                "retrieval": retrieval,
                            }
                        ),
                    },
                ],
            )
            raw = provider.chat(request).content
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        if "decision" not in payload:
            payload = {
                "decision": "search_and_complete",
                "execution_mode": "search",
                "tool_target": "map_search",
                "should_trigger_search": True,
                "location_status": "valid" if (has_coordinates or has_text_location) else "missing",
                "requires_geocoding": bool(has_text_location and not has_coordinates),
                "selected_basemap_id": None,
                "selected_overlay_ids": [],
                "clarification_question": None,
                "chat_instructions": {
                    "tone": "clear_and_direct",
                    "must_explain_limitations": True,
                    "must_offer_refinements": True,
                    "must_confirm_search_start": False,
                },
                "reasoning_summary": "Fallback deterministic decision",
                "feasibility": {"is_supported": True, "blocking_reason": None},
            }
        payload.setdefault("execution_mode", "search" if payload.get("should_trigger_search") else "clarify")
        payload.setdefault(
            "tool_target",
            "map_search" if payload.get("execution_mode") == "search" else None,
        )
        return AgentDecision.model_validate(payload)
