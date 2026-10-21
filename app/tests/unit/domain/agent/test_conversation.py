from __future__ import annotations

import pytest

from server.domain.agent.conversation import ConversationState, PendingClarification

###############################################################################
def test_other_conversation_state_schema_versions_are_rejected() -> None:
    for schema_version in (1, 3):
        with pytest.raises(ValueError, match="schema_version"):
            ConversationState.from_persisted(
                "conversation-future",
                {
                    "schema_version": schema_version,
                    "conversation_id": "conversation-future",
                },
            )

###############################################################################
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

###############################################################################
def test_generic_unrelated_turn_does_not_answer_clarification() -> None:
    state = ConversationState.from_persisted(
        "conversation-3",
        {
            "conversation_id": "conversation-3",
            "pending_clarification": {
                "question": "Which country contains Lake Bracciano?",
                "source_turn_index": 1,
            },
        },
    )

    assert state.context_projection("Hello")["pending_clarification"] is None
    deferred = state.clarification_after_turn("Hello")
    assert deferred is not None
    assert deferred.status == "deferred"

###############################################################################
def test_direct_answer_resolves_and_preserves_terminal_clarification() -> None:
    state = ConversationState.from_persisted(
        "conversation-4",
        {
            "conversation_id": "conversation-4",
            "pending_clarification": {
                "question": "Which country contains Lake Bracciano?",
                "source_turn_index": 1,
            },
        },
    )

    answered = state.clarification_after_turn("Italy")
    assert answered is not None
    assert answered.status == "answered"
    answered_state = state.model_copy(update={"pending_clarification": answered})
    preserved = answered_state.clarification_after_turn("Hello")
    assert preserved is not None
    assert preserved.status == "answered"

###############################################################################
def test_infrastructure_option_matching_uses_word_boundaries() -> None:
    clarification = PendingClarification.from_turn(
        "Which infrastructure category do you need?",
        source_turn_index=1,
        source_text="Show infrastructure in Rome",
    )

    assert clarification.match_option("EV charging stations") == "ev_charging"
    assert clarification.match_option("level crossings") is None
