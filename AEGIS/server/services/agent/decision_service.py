from __future__ import annotations

import json
import re
from typing import Any

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.prompts import get_agent_decision_system_prompt
from AEGIS.server.services.llm.types import ChatCompletionRequest


class DecisionService:
    GEOCODE_PATTERNS = (
        re.compile(r"\b(coordinates?|latitude|longitude|lat\s*/\s*lon|lat[- ]?lon)\b", re.IGNORECASE),
        re.compile(r"\b(where is\b|\bgeocode\b|\blocat(?:e|ion of)\b)", re.IGNORECASE),
    )
    DIRECT_WEATHER_PATTERNS = (
        re.compile(r"\b(weather forecast|forecast weather|weather outlook)\b", re.IGNORECASE),
    )
    DIRECT_AIR_QUALITY_PATTERNS = (
        re.compile(r"\b(air quality forecast|forecast air quality|pollution forecast)\b", re.IGNORECASE),
    )
    DIRECT_POI_PATTERNS = (
        re.compile(r"\b(nearby poi|nearby amenities|points of interest|nearby places)\b", re.IGNORECASE),
    )
    AMBIGUOUS_REQUEST_PATTERNS = (
        re.compile(r"\b(best|ideal|optimum|optimize|most suitable)\b", re.IGNORECASE),
    )
    INTEGRATION_KEYWORDS = {
        "tomtom": "TomTom",
        "geoapify": "Geoapify",
        "openaq": "OpenAQ",
        "pvgis": "PVGIS",
    }
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
    ACTION_VERBS = {
        "find",
        "show",
        "center",
        "near",
        "around",
        "check",
        "compare",
        "locate",
        "map",
        "inspect",
    }
    LOCATION_CUE_PATTERNS = (
        re.compile(r"\b(?:near|nearby|around|at|in)\s+[a-z0-9][a-z0-9\s,'\-]{2,}", re.IGNORECASE),
        re.compile(r"\b\d{1,5}\s+[a-z0-9][a-z0-9\s.'\-]{2,}", re.IGNORECASE),
        re.compile(r"\b(?:street|st|road|rd|avenue|ave|via|boulevard|blvd|lane|ln|square|piazza)\b", re.IGNORECASE),
        re.compile(r"[+-]?\d{1,2}(?:\.\d+)?\s*[, ]\s*[+-]?\d{1,3}(?:\.\d+)?", re.IGNORECASE),
    )

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
        if any(keyword in haystack for keyword in self.GEOSPATIAL_KEYWORDS):
            return True
        if self._looks_like_location_phrase(user_message):
            normalized = user_message.lower()
            return any(verb in normalized for verb in self.ACTION_VERBS)
        return False

    def _looks_like_location_phrase(self, user_message: str) -> bool:
        normalized = user_message.strip().lower()
        if any(pattern.search(normalized) for pattern in self.LOCATION_CUE_PATTERNS):
            return True
        if "," in normalized and any(token in normalized for token in ("switzerland", "italy", "france", "usa", "uk")):
            return True
        return False

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
                "blocking_reason": "I can help with location-based geospatial requests and coordinate lookup.",
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
            clarification_question="Which specific location should I focus on for this request?",
            reasoning_summary="Ambiguous geospatial goal",
        )

    def _build_missing_location_decision(self) -> AgentDecision:
        return AgentDecision(
            decision="clarify",
            execution_mode="clarify",
            tool_target=None,
            should_trigger_search=False,
            location_status="missing",
            requires_geocoding=False,
            clarification_question="Which location should I search on the map? You can provide a city, full address, or coordinates.",
            reasoning_summary="Missing location",
        )

    def _build_low_confidence_geocode_attempt_decision(self) -> AgentDecision:
        return AgentDecision(
            decision="search_and_complete",
            execution_mode="geocode",
            tool_target="location_to_coordinates",
            should_trigger_search=False,
            location_status="partial",
            requires_geocoding=True,
            clarification_question=None,
            reasoning_summary="Low-confidence parse with likely location intent; attempt geocode once",
        )

    def _build_missing_integration_decision(self, integration_name: str) -> AgentDecision:
        return AgentDecision(
            decision="clarify",
            execution_mode="clarify",
            tool_target=None,
            should_trigger_search=False,
            location_status="valid",
            requires_geocoding=False,
            clarification_question=(
                f"I can use {integration_name} for this request, but its API key is not configured. "
                f"Would you like to add the key or use an available alternative layer?"
            ),
            reasoning_summary="Missing required integration",
        )

    def _build_geocode_decision(self, has_text_location: bool, has_coordinates: bool) -> AgentDecision:
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

    def _build_direct_tool_decision(
        self,
        *,
        tool_target: str,
        has_text_location: bool,
        has_coordinates: bool,
        summary: str,
    ) -> AgentDecision:
        return AgentDecision(
            decision="search_and_complete",
            execution_mode="search",
            tool_target=tool_target,
            should_trigger_search=False,
            location_status="valid" if (has_text_location or has_coordinates) else "missing",
            requires_geocoding=has_text_location and not has_coordinates,
            clarification_question=None,
            reasoning_summary=summary,
        )

    def _select_available_candidate_ids(self, retrieval: dict[str, list[dict[str, object]]], kind: str) -> list[str]:
        selected: list[str] = []
        for item in retrieval.get(kind, []):
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if not isinstance(item_id, str):
                continue
            if bool(item.get("is_available", True)):
                selected.append(item_id)
        return selected

    def _requested_integration(self, user_message: str) -> tuple[str, str] | None:
        normalized = user_message.lower()
        for keyword, label in self.INTEGRATION_KEYWORDS.items():
            if keyword in normalized:
                return keyword, label
        return None

    def _integration_blocked(self, *, retrieval: dict[str, list[dict[str, object]]], keyword: str) -> bool:
        matching: list[dict[str, object]] = []
        for kind in ("basemaps", "overlays"):
            for item in retrieval.get(kind, []):
                if not isinstance(item, dict):
                    continue
                haystack = " ".join(
                    [
                        str(item.get("id") or ""),
                        str(item.get("label") or ""),
                        str(item.get("provider") or ""),
                    ]
                ).lower()
                if keyword in haystack:
                    matching.append(item)
        if not matching:
            return False
        return all(not bool(item.get("is_available", True)) for item in matching)

    def _default_search_payload(self, has_coordinates: bool, has_text_location: bool) -> dict[str, Any]:
        return {
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

    def decide(
        self,
        *,
        conversation_context: str,
        user_message: str,
        extracted_state: ExtractedIntent,
        retrieval: dict[str, list[dict[str, object]]],
        available_tools: list[dict[str, str]] | None = None,
    ) -> AgentDecision:
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
        if is_geocode_request:
            return self._build_geocode_decision(has_text_location, has_coordinates)
        if has_coordinates:
            return AgentDecision(
                decision="search_and_complete",
                execution_mode="search",
                tool_target="map_search",
                should_trigger_search=True,
                location_status="valid",
                requires_geocoding=False,
                clarification_question=None,
                reasoning_summary="Coordinates available for deterministic map search",
            )
        if not has_coordinates and not has_text_location:
            if self._looks_like_location_phrase(user_message) and extracted_state.certainty < 0.55:
                return self._build_low_confidence_geocode_attempt_decision()
            return self._build_missing_location_decision()
        if any(pattern.search(user_message) for pattern in self.DIRECT_WEATHER_PATTERNS):
            return self._build_direct_tool_decision(
                tool_target="get_weather_forecast",
                has_text_location=has_text_location,
                has_coordinates=has_coordinates,
                summary="Direct weather forecast request",
            )
        if any(pattern.search(user_message) for pattern in self.DIRECT_AIR_QUALITY_PATTERNS):
            return self._build_direct_tool_decision(
                tool_target="get_air_quality_forecast",
                has_text_location=has_text_location,
                has_coordinates=has_coordinates,
                summary="Direct air-quality forecast request",
            )
        if any(pattern.search(user_message) for pattern in self.DIRECT_POI_PATTERNS):
            return self._build_direct_tool_decision(
                tool_target="get_nearby_poi",
                has_text_location=has_text_location,
                has_coordinates=has_coordinates,
                summary="Direct nearby POI request",
            )

        requested_integration = self._requested_integration(user_message)
        if requested_integration is not None:
            keyword, label = requested_integration
            any_available = bool(self._select_available_candidate_ids(retrieval, "basemaps") or self._select_available_candidate_ids(retrieval, "overlays"))
            if self._integration_blocked(retrieval=retrieval, keyword=keyword) and not any_available:
                return self._build_missing_integration_decision(label)

        try:
            provider = self.llm_factory.get_agent_provider(self.provider)
            request = ChatCompletionRequest(
                model=self.model,
                messages=[
                    {"role": "system", "content": get_agent_decision_system_prompt(provider=self.provider, model=self.model)},
                    {"role": "user", "content": conversation_context},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "user_message": user_message,
                                "available_tools": available_tools or [],
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
            payload = self._default_search_payload(has_coordinates, has_text_location)
        payload.setdefault("execution_mode", "search" if payload.get("should_trigger_search") else "clarify")
        payload.setdefault("tool_target", "map_search" if payload.get("execution_mode") == "search" else None)
        if has_coordinates and payload.get("execution_mode") == "clarify":
            payload.update(
                {
                    "decision": "search_and_complete",
                    "execution_mode": "search",
                    "tool_target": "map_search",
                    "should_trigger_search": True,
                    "location_status": "valid",
                    "requires_geocoding": False,
                    "clarification_question": None,
                    "reasoning_summary": "Coordinates provided; force map-search execution",
                }
            )
        allowed_basemaps = set(self._select_available_candidate_ids(retrieval, "basemaps"))
        allowed_overlays = set(self._select_available_candidate_ids(retrieval, "overlays"))
        selected_basemap_id = payload.get("selected_basemap_id")
        if isinstance(selected_basemap_id, str) and selected_basemap_id and selected_basemap_id not in allowed_basemaps:
            payload["selected_basemap_id"] = None
        selected_overlays = payload.get("selected_overlay_ids")
        if isinstance(selected_overlays, list):
            payload["selected_overlay_ids"] = [item for item in selected_overlays if isinstance(item, str) and item in allowed_overlays]
        return AgentDecision.model_validate(payload)
