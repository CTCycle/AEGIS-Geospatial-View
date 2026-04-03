from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from AEGIS.server.domain.chat import ChatTurnRequest, ChatTurnResponse
from AEGIS.server.domain.geographics import LocationSearchRequest
from AEGIS.server.repositories.chat_history import ChatHistoryRepository
from AEGIS.server.repositories.model_settings import ModelSettingsRepository
from AEGIS.server.services.agent.executor import infer_datetime, requires_follow_up
from AEGIS.server.services.agent.prompts import AGENT_INTENT_SYSTEM_PROMPT
from AEGIS.server.services.chat.settings_service import ChatSettingsService
from AEGIS.server.services.geospatial.manifest_loader import GeospatialManifestLoader
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.structured import INTENT_SCHEMA, normalize_structured_payload
from AEGIS.server.services.llm.types import ChatCompletionRequest
from AEGIS.server.services.search.intent_mapper import map_structured_intent_to_location_request
from AEGIS.server.services.search.planner import SearchPlanner
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator
from AEGIS.server.services.vector.retriever import VectorRetriever


class AgentOrchestrator:
    def __init__(
        self,
        *,
        search_orchestrator: LocationSearchOrchestrator,
        history_repo: ChatHistoryRepository | None = None,
        settings_repo: ModelSettingsRepository | None = None,
        settings_service: ChatSettingsService | None = None,
        llm_factory: LLMFactory | None = None,
        vector_retriever: VectorRetriever | None = None,
        planner: SearchPlanner | None = None,
        manifest_loader: GeospatialManifestLoader | None = None,
    ) -> None:
        self.search_orchestrator = search_orchestrator
        self.history_repo = history_repo or ChatHistoryRepository()
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self.settings_service = settings_service or ChatSettingsService()
        self.llm_factory = llm_factory or LLMFactory()
        self.vector_retriever = vector_retriever or VectorRetriever()
        self.planner = planner or SearchPlanner()
        self.manifest_loader = manifest_loader or GeospatialManifestLoader()

    def _heuristic_intent(self, text: str, *, explicit_datetime: str | None) -> dict[str, Any]:
        coordinates_match = re.search(
            r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)",
            text,
        )
        coordinates = None
        if coordinates_match:
            coordinates = {
                "latitude": float(coordinates_match.group(1)),
                "longitude": float(coordinates_match.group(2)),
            }
        bbox_match = re.search(
            r"\[\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\]",
            text,
        )
        bbox = None
        if bbox_match:
            bbox = [
                float(bbox_match.group(1)),
                float(bbox_match.group(2)),
                float(bbox_match.group(3)),
                float(bbox_match.group(4)),
            ]
        map_type = "auto"
        text_lower = text.lower()
        if "satellite" in text_lower:
            map_type = "satellite"
        elif "terrain" in text_lower:
            map_type = "terrain"
        elif "street" in text_lower:
            map_type = "streets"
        requested_overlays: list[str] = []
        overlay_map = {
            "traffic": "tomtom_traffic_flow",
            "air quality": "openaq_air_quality",
            "solar": "pvgis_solar",
            "noise": "eea_noise_2019",
            "wildfire": "GIBS_MODIS_Combined_Thermal_Anomalies_Fire",
        }
        for phrase, overlay_id in overlay_map.items():
            if phrase in text_lower:
                requested_overlays.append(overlay_id)
        return normalize_structured_payload(
            {
                "request_text": text,
                "location": {
                    "text": None if coordinates or bbox else text,
                    "coordinates": coordinates,
                    "bbox": bbox,
                },
                "display_area": {
                    "mode": "bbox" if bbox else ("point" if coordinates else "inferred"),
                    "radius_m": 2500.0,
                    "bbox": bbox,
                },
                "view": {
                    "view_mode": "interactive_map",
                    "map_type": map_type,
                },
                "overlays": {"requested": requested_overlays},
                "planning": {
                    "user_intent": "map_search",
                    "datetime_inference": explicit_datetime or datetime.now(UTC).isoformat(),
                    "confidence": 0.5,
                    "missing_information": [],
                    "should_execute_search": True,
                    "follow_up_question": None,
                },
            }
        )

    def _extract_intent(self, text: str, *, explicit_datetime: str | None) -> dict[str, Any]:
        settings = self.settings_repo.get_or_create()
        provider = self.llm_factory.get_provider(settings.agent_model_provider)
        request = ChatCompletionRequest(
            model=settings.agent_model_name,
            messages=[
                {"role": "system", "content": AGENT_INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        try:
            payload = provider.structured_output(request, schema=INTENT_SCHEMA)
            if payload:
                if isinstance(payload, str):
                    normalized = normalize_structured_payload({"request_text": payload})
                elif isinstance(payload, dict):
                    normalized = normalize_structured_payload(payload)
                else:
                    normalized = normalize_structured_payload({})
                if explicit_datetime:
                    normalized["planning"]["datetime_inference"] = explicit_datetime
                else:
                    normalized["planning"]["datetime_inference"] = infer_datetime(normalized["planning"])
                return normalized
        except Exception:
            pass
        return self._heuristic_intent(text, explicit_datetime=explicit_datetime)

    async def run_turn(self, request: ChatTurnRequest) -> ChatTurnResponse:
        session = self.history_repo.upsert_session(request.session_id, title=request.title)
        self.history_repo.append_message(
            session_id=session.id,
            role="user",
            content=request.message,
        )
        intent = self._extract_intent(request.message, explicit_datetime=request.datetime)
        retrieval = self.vector_retriever.retrieve_candidates(request.message)
        plan = self.planner.plan(
            intent=intent,
            retrieval=retrieval,
            manifests=self.manifest_loader.load_all(),
        )
        intent.setdefault("overlays", {})
        intent["overlays"]["requested"] = plan.selected_overlay_ids
        intent.setdefault("planning", {})
        if plan.follow_up_reason and not intent["planning"].get("follow_up_question"):
            intent["planning"]["follow_up_question"] = (
                "Please clarify the location or map extent so I can execute this search."
            )
            intent["planning"]["missing_information"] = [plan.follow_up_reason]
            intent["planning"]["should_execute_search"] = False
        if requires_follow_up(intent):
            follow_up = str(
                intent.get("planning", {}).get("follow_up_question")
                or "Could you clarify the requested location or display area?"
            )
            self.history_repo.append_message(
                session_id=session.id,
                role="assistant",
                content=follow_up,
                structured_payload=intent,
            )
            return ChatTurnResponse(
                session_id=session.id,
                assistant_message=follow_up,
                structured_intent=intent,
                map_session=None,
                tool_payload={"execution": "follow_up"},
                follow_up_required=True,
            )

        mapped_payload = map_structured_intent_to_location_request(
            {
                **intent,
                "datetime": intent.get("planning", {}).get("datetime_inference") or datetime.now(UTC).isoformat(),
                "overlay_ids": plan.selected_overlay_ids,
                "base_map": plan.selected_basemap_id,
            }
        )
        location_request = LocationSearchRequest.model_validate(mapped_payload)
        result = await self.search_orchestrator.execute(location_request)
        assistant_message = (
            f"Resolved location: {intent.get('location', {}).get('text') or 'coordinates'}, "
            f"display area: {plan.selected_display_area.get('mode', 'inferred')}, "
            f"basemap: {plan.selected_basemap_id}, "
            f"overlays: {', '.join(plan.selected_overlay_ids) if plan.selected_overlay_ids else 'none'}."
        )
        self.history_repo.append_message(
            session_id=session.id,
            role="assistant",
            content=assistant_message,
            structured_payload=intent,
            tool_payload={"execution": "search"},
            map_session=result.get("map_session"),
        )
        return ChatTurnResponse(
            session_id=session.id,
            assistant_message=assistant_message,
            structured_intent=intent,
            map_session=result.get("map_session"),
            tool_payload=result.get("payload"),
            follow_up_required=False,
        )
