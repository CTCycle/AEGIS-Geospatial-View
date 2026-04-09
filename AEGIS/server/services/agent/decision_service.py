from __future__ import annotations

import json

from AEGIS.server.domain.agent.decision import AgentDecision
from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.prompts import AGENT_DECISION_SYSTEM_PROMPT
from AEGIS.server.services.llm.types import ChatCompletionRequest

###############################################################################
class DecisionService:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

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
        if not has_coordinates and not has_text_location:
            return AgentDecision(
                decision="clarify",
                should_trigger_search=False,
                location_status="missing",
                requires_geocoding=False,
                clarification_question="Which location should I search on the map?",
                reasoning_summary="Missing location",
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
        return AgentDecision.model_validate(payload)
