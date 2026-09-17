from __future__ import annotations

from server.domain.agent.conversation import ConversationState


def test_legacy_unresolved_question_migrates_and_is_scoped() -> None:
    state = ConversationState.from_persisted(
        "conversation-1",
        {
            "schema_version": 1,
            "conversation_id": "conversation-1",
            "unresolved_questions": ["Which country contains Lake Bracciano?"],
        },
    )

    assert state.schema_version == 2
    assert state.pending_clarification is not None
    assert state.pending_clarification.status == "active"
    assert state.context_projection("Add an environmental layer")[
        "pending_clarification"
    ] is None
    assert state.context_projection("Italy")["unresolved_questions"] == [
        "Which country contains Lake Bracciano?"
    ]


def test_unrelated_turn_defers_but_does_not_delete_clarification() -> None:
    state = ConversationState.from_persisted(
        "conversation-2",
        {
            "conversation_id": "conversation-2",
            "pending_clarification": {
                "question": "Which country contains Lake Bracciano?",
                "source_turn_index": 1,
                "scope_terms": ["lake", "bracciano"],
            },
        },
    )

    projection = state.context_projection("Add an environmental layer")
    assert projection["pending_clarification"] is None
    assert state.pending_clarification is not None
    assert state.pending_clarification.question.endswith("Bracciano?")
