from __future__ import annotations

import asyncio

from AEGIS.server.domain.chat import ChatTurnRequest
from AEGIS.server.services.agent.orchestrator import AgentOrchestrator


class _VectorRetrieverStub:
    def retrieve_candidates(self, query, *, top_k=8):  # noqa: ANN001
        return {"basemaps": [], "overlays": [], "providers": []}


class _SearchOrchestratorStub:
    nominatim_service = object()
    catalog_service = object()

    async def execute(self, payload):  # noqa: ANN001
        return {
            "payload": {"ok": True},
            "map_session": {
                "center": {"latitude": payload.latitude, "longitude": payload.longitude},
                "bounds": [12.4, 41.8, 12.6, 42.0],
            },
        }


class _FailingFactory:
    def get_parser_provider(self, provider: str):  # noqa: ARG002
        raise RuntimeError("parser unavailable")

    def get_agent_provider(self, provider: str):  # noqa: ARG002
        raise RuntimeError("agent unavailable")

    def get_chat_provider(self, provider: str):  # noqa: ARG002
        raise RuntimeError("chat unavailable")


def test_chat_orchestrator_falls_back_when_llm_unavailable_for_coordinate_prompt(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(AgentOrchestrator, "_check_ollama_availability", lambda self, settings: (True, None))
    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        llm_factory=_FailingFactory(),
        vector_retriever=_VectorRetrieverStub(),
    )

    result = asyncio.run(
        orchestrator.run_turn(ChatTurnRequest(message="show map at 41.9028, 12.4964"))
    )

    assert result.map_session is not None
    assert "map search" in result.assistant_message.lower()
    assert result.extracted_state is not None
    assert result.extracted_state["coordinates"]["latitude"] == 41.9028
    assert result.extracted_state["coordinates"]["longitude"] == 12.4964
