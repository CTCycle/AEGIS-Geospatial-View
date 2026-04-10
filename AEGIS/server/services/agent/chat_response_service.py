from __future__ import annotations

import json
import re
from typing import Any

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.prompts import AGENT_RESPONSE_PROMPT
from AEGIS.server.services.llm.types import ChatCompletionRequest


class ChatResponseService:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

    def _sanitize_retrieval_for_chat(self, retrieval: dict[str, list[dict[str, object]]]) -> dict[str, list[dict[str, object]]]:
        sanitized: dict[str, list[dict[str, object]]] = {"basemaps": [], "overlays": [], "providers": []}
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

    def _sanitize_search_result_for_chat(self, search_result: dict[str, Any] | None) -> dict[str, Any] | None:
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

    def _fallback_response(self, decision: AgentDecision, search_result: dict[str, Any] | None) -> str:
        if not decision.feasibility.is_supported:
            return decision.feasibility.blocking_reason or "I can only help with location-based geospatial requests."
        geocode_result = search_result.get("geocode_result") if isinstance(search_result, dict) else None
        if decision.execution_mode == "geocode":
            if isinstance(geocode_result, dict):
                latitude = geocode_result.get("lat")
                longitude = geocode_result.get("lon")
                if latitude is not None and longitude is not None:
                    return f"The coordinates are latitude {latitude} and longitude {longitude}."
            return "I could not resolve coordinates for that location. Please share a more specific place name."
        if decision.execution_mode == "search" and search_result is not None:
            return "I completed the map search and prepared the requested geospatial view."
        if decision.clarification_question:
            return decision.clarification_question
        if "integration" in (decision.reasoning_summary or "").lower():
            return "I need a required integration key to complete this exact request."
        return "I need a bit more detail to continue with the map request."

    def generate(
        self,
        *,
        conversation_context: str,
        user_message: str,
        extracted_state: ExtractedIntent,
        decision: AgentDecision,
        retrieval: dict[str, list[dict[str, object]]],
        search_result: dict[str, Any] | None,
    ) -> str:
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
            }
            result = provider.chat(
                ChatCompletionRequest(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": AGENT_RESPONSE_PROMPT},
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
