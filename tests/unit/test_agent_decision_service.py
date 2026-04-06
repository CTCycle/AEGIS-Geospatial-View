from __future__ import annotations

from AEGIS.server.domain.extraction.models import ExtractedIntent
from AEGIS.server.services.agent.decision_service import DecisionService
from AEGIS.server.services.llm.factory import LLMFactory


def test_decision_service_requires_location() -> None:
    service = DecisionService(llm_factory=LLMFactory(), provider="ollama", model="llama3.2")
    decision = service.decide(
        user_message="show traffic",
        extracted_state=ExtractedIntent(),
        retrieval={"basemaps": [], "overlays": [], "providers": []},
    )
    assert decision.decision == "clarify"
    assert decision.should_trigger_search is False
