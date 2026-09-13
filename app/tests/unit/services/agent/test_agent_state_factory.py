from __future__ import annotations

import pytest

from server.domain.agent.context import AgentContextPackage, ConversationDirective
from server.services.agent.agent_state_factory import AgentStateFactory


###############################################################################
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


###############################################################################
def test_factory_hydrates_the_complete_native_context_package() -> None:
    package = AgentContextPackage(
        current_user_message="show traffic",
        active_instructions=[
            ConversationDirective(
                directive_id="directive-1",
                normalized_text="exclude motorways",
                original_user_text="exclude motorways",
                source_turn_index=1,
            )
        ],
        task_state={"active_task_id": "task-1"},
        map_memory={"revision": 4},
        conversation_summary={"through_turn_index": 2},
        recent_messages=[{"role": "assistant", "content": "Previous result."}],
        relevant_tool_outcomes=[{"evidence_id": "evidence:1"}],
        policy_constraints={"allowed_tool_names": ["discover"]},
        included_message_ids=[1, 3],
        omitted_message_ids=[2],
        summarized_through_turn_index=2,
        context_allocation={"usable_input_tokens": 1000},
    )

    state = AgentStateFactory.create(
        request_id="request-1",
        conversation_id="conversation-1",
        user_message="show traffic",
        context_package=package,
    )

    assert state.context_hydrated is True
    assert state.active_instructions[0]["normalized_text"] == "exclude motorways"
    assert state.task_state == {"active_task_id": "task-1"}
    assert state.map_memory == {"revision": 4}
    assert state.recent_messages[0]["role"] == "assistant"
    assert state.relevant_tool_outcomes[0]["evidence_id"] == "evidence:1"
    assert state.policy_constraints == {"allowed_tool_names": ["discover"]}
    assert state.included_message_ids == [1, 3]
    assert state.omitted_message_ids == [2]
    assert state.summarized_through_turn_index == 2


###############################################################################
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
