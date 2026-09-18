from __future__ import annotations

from server.domain.agent.conversation import ConversationState, PendingClarification


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
    projection = state.context_projection("Italy")
    assert projection["pending_clarification"]["question"] == (
        "Which country contains Lake Bracciano?"
    )
    assert "unresolved_questions" not in projection
    assert "unresolved_questions" not in state.model_dump(mode="json")


def test_future_conversation_state_schema_is_rejected() -> None:
    try:
        ConversationState.from_persisted(
            "conversation-future",
            {
                "schema_version": 3,
                "conversation_id": "conversation-future",
            },
        )
    except ValueError as exc:
        assert str(exc) == "Unsupported conversation state schema version."
    else:
        raise AssertionError("Future conversation state schema was accepted.")


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


def test_infrastructure_option_matching_uses_word_boundaries() -> None:
    clarification = PendingClarification.from_turn(
        "Which infrastructure category do you need?",
        source_turn_index=1,
        source_text="Show infrastructure in Rome",
    )

    assert clarification.match_option("EV charging stations") == "ev_charging"
    assert clarification.match_option("level crossings") is None
