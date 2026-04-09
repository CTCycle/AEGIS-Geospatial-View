from __future__ import annotations

import asyncio

from AEGIS.server.domain.chat import ChatTurnRequest
from AEGIS.server.services.agent.orchestrator import AgentOrchestrator


class _SearchOrchestratorStub:
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


def test_chat_orchestrator_falls_back_when_llm_unavailable_for_coordinate_prompt() -> None:
    orchestrator = AgentOrchestrator(
        search_orchestrator=_SearchOrchestratorStub(),
        llm_factory=_FailingFactory(),
    )

    result = asyncio.run(
        orchestrator.run_turn(ChatTurnRequest(message="show map at 41.9028, 12.4964"))
    )

    assert result.map_session is not None
    assert result.assistant_message == "Search executed successfully."
    assert result.extracted_state is not None
    assert result.extracted_state["coordinates"]["latitude"] == 41.9028
    assert result.extracted_state["coordinates"]["longitude"] == 12.4964
