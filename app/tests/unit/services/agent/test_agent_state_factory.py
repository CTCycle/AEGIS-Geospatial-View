from __future__ import annotations

import pytest

from server.services.agent.agent_state_factory import AgentStateFactory


def test_factory_creates_bounded_receive_state() -> None:
    state = AgentStateFactory.create(
        request_id="request-1",
        conversation_id="conversation-1",
        user_message="  show traffic  ",
        evidence_refs=["evidence:1", "evidence:1"],
    )

    assert state.user_message == "show traffic"
    assert state.phase.value == "receive_request"
    assert state.evidence_refs == ["evidence:1"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"request_id": "r", "conversation_id": "c", "user_message": ""},
        {"request_id": "", "conversation_id": "c", "user_message": "hello"},
    ],
)
def test_factory_rejects_invalid_lifecycle_inputs(kwargs: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        AgentStateFactory.create(**kwargs)
