from __future__ import annotations

import json
import re
from typing import Any

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.prompts import get_agent_response_prompt
from AEGIS.server.services.llm.types import ChatCompletionRequest


###############################################################################
class ChatResponseService:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

    def _sanitize_retrieval_for_chat(
        self, retrieval: dict[str, list[dict[str, object]]]
    ) -> dict[str, list[dict[str, object]]]:
        sanitized: dict[str, list[dict[str, object]]] = {
            "basemaps": [],
            "overlays": [],
            "providers": [],
        }
        for kind in ("basemaps", "overlays"):
            for item in retrieval.get(kind, []):
                if not isinstance(item, dict):
                    continue
                sanitized[kind].append(
                    {
                        "label": item.get("label") or item.get("id"),
                        "provider": item.get("provider"),
                        "score": item.get("score"),
                        "is_available": item.get("is_available", True),
                        "availability_reason": item.get("availability_reason"),
                        "summary": item.get("summary"),
                    }
                )
        return sanitized

    def _sanitize_search_result_for_chat(
        self, search_result: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if not isinstance(search_result, dict):
            return None
        geocode = search_result.get("geocode_result")
        if isinstance(geocode, dict):
            return {
                "geocode_result": {
                    "lat": geocode.get("lat"),
                    "lon": geocode.get("lon"),
                    "display_name": geocode.get("display_name"),
                }
            }
        map_session = search_result.get("map_session")
        if isinstance(map_session, dict):
            overlays = map_session.get("overlays")
            overlay_count = len(overlays) if isinstance(overlays, list) else 0
            return {
                "map_session": {
                    "center": map_session.get("center"),
                    "overlay_count": overlay_count,
                    "status": "ready",
                }
            }
        tool_result = search_result.get("tool_result")
        if isinstance(tool_result, dict):
            sanitized = dict(tool_result)
            if "items" in sanitized and isinstance(sanitized["items"], list):
                sanitized["items"] = sanitized["items"][:8]
            return {
                "tool_result": sanitized,
                "resolved_coordinates": search_result.get("resolved_coordinates"),
            }
        return {"status": "completed"}

    def _normalize_plain_text_response(self, text: str) -> str:
        value = (text or "").strip()
        if not value:
            return ""
        value = re.sub(r"```[\s\S]*?```", " ", value)
        value = re.sub(r"`([^`]*)`", r"\1", value)
        value = re.sub(r"[*_#>\[\]{}|]", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        if value.startswith("{") and value.endswith("}"):
            return ""
        if value.startswith("[") and value.endswith("]"):
            return ""
        return value

    def _fallback_response(
        self, decision: AgentDecision, search_result: dict[str, Any] | None
    ) -> str:
        if not decision.feasibility.is_supported:
            return (
                decision.feasibility.blocking_reason
                or "I can only help with location-based geospatial requests."
            )
        geocode_result = (
            search_result.get("geocode_result")
            if isinstance(search_result, dict)
            else None
        )
        if decision.execution_mode == "geocode":
            if isinstance(geocode_result, dict):
                latitude = geocode_result.get("lat")
                longitude = geocode_result.get("lon")
                if latitude is not None and longitude is not None:
                    return f"The coordinates are latitude {latitude} and longitude {longitude}."
            return "I could not resolve coordinates for that location. Please share a more specific place name."
        if decision.execution_mode == "search" and search_result is not None:
            if isinstance(search_result, dict) and isinstance(
                search_result.get("tool_result"), dict
            ):
                tool_result = search_result["tool_result"]
                if tool_result.get("kind") == "weather_forecast":
                    return "I retrieved the weather forecast for that location."
                if tool_result.get("kind") == "air_quality_forecast":
                    return "I retrieved the air-quality forecast for that location."
                if tool_result.get("kind") == "poi_amenities":
                    total = tool_result.get("total_results")
                    if isinstance(total, int):
                        return f"I found {total} nearby points of interest for that location."
                    return "I retrieved nearby points of interest for that location."
            map_session = (
                search_result.get("map_session")
                if isinstance(search_result, dict)
                else None
            )
            payload = (
                search_result.get("payload")
                if isinstance(search_result, dict)
                else None
            )
            overlay_count = 0
            if isinstance(map_session, dict):
                overlays = map_session.get("overlays")
                if isinstance(overlays, list):
                    overlay_count = len(overlays)
            unmet_filters: list[str] = []
            if isinstance(payload, dict) and isinstance(
                payload.get("unmet_filters"), list
            ):
                unmet_filters = [
                    str(value)
                    for value in payload["unmet_filters"]
                    if str(value).strip()
                ]
            requested_overlay_intent = bool(
                isinstance(decision.selected_overlay_ids, list)
                and decision.selected_overlay_ids
            )
            if requested_overlay_intent and overlay_count == 0:
                if unmet_filters:
                    return (
                        "I could not apply all requested overlays for this location. "
                        f"Unmet filters: {', '.join(unmet_filters)}. Try a narrower overlay request."
                    )
                return "I completed the map search, but no matching overlays were available for this request."
            return (
                "I completed the map search and prepared the requested geospatial view."
            )
        if decision.clarification_question:
            return decision.clarification_question
        if "integration" in (decision.reasoning_summary or "").lower():
            return "I need a required integration key to complete this exact request."
        return "I need a bit more detail to continue with the map request."

    def _deterministic_clarification(
        self,
        *,
        decision: AgentDecision,
        search_result: dict[str, Any] | None,
    ) -> str | None:
        if "location" in decision.missing_fields:
            if decision.tool_target == "location_to_coordinates":
                return "Which location should I convert to coordinates?"
            return "Which location should I show on the map?"
        if decision.clarification_kind == "integration_blocked":
            return decision.clarification_question
        if decision.execution_mode == "geocode":
            geocode_result = (
                search_result.get("geocode_result")
                if isinstance(search_result, dict)
                else None
            )
            if geocode_result is None:
                return "I couldn't resolve that place yet. Can you share a more specific location?"
        return None

    def generate(
        self,
        *,
        conversation_context: str,
        user_message: str,
        extracted_state: ExtractedIntent,
        decision: AgentDecision,
        retrieval: dict[str, list[dict[str, object]]],
        search_result: dict[str, Any] | None,
        execution_feedback: dict[str, Any] | None = None,
    ) -> str:
        deterministic_clarification = self._deterministic_clarification(
            decision=decision,
            search_result=search_result,
        )
        if deterministic_clarification:
            return deterministic_clarification
        sanitized_retrieval = self._sanitize_retrieval_for_chat(retrieval)
        sanitized_search_result = self._sanitize_search_result_for_chat(search_result)
        try:
            provider = self.llm_factory.get_chat_provider(self.provider)
            payload = {
                "user_message": user_message,
                "extracted_state": extracted_state.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "retrieval": sanitized_retrieval,
                "search_result": sanitized_search_result,
                "execution_feedback": execution_feedback
                or {"status": "unknown", "errors": [], "ambiguities": []},
            }
            result = provider.chat(
                ChatCompletionRequest(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": get_agent_response_prompt(
                                provider=self.provider, model=self.model
                            ),
                        },
                        {"role": "user", "content": conversation_context},
                        {"role": "user", "content": json.dumps(payload, default=str)},
                    ],
                )
            )
            text = self._normalize_plain_text_response((result.content or "").strip())
            if text:
                return text
        except Exception:
            pass
        return self._fallback_response(decision, search_result)
