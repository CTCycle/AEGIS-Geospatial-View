from __future__ import annotations

import sqlalchemy
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.contracts.events import RunEventCreate, RunEventType, RunEventVisibility
from server.repositories.agent_run_events import AgentRunEventRepository
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.chat_history import ChatHistoryRepository
from server.repositories.conversations import ConversationRepository
from server.repositories.schemas.models import Base


class _InMemoryBackend:
    db_path = None

    def __init__(self) -> None:
        self.engine = sqlalchemy.create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.session = sessionmaker(bind=self.engine, future=True)


def _backend() -> _InMemoryBackend:
    backend = _InMemoryBackend()
    Base.metadata.create_all(backend.engine)
    return backend


def test_history_search_is_scoped_bounded_and_deterministic() -> None:
    backend = _backend()
    conversations = ConversationRepository(backend)
    history = ChatHistoryRepository(backend)
    first = conversations.create_conversation("Rome planning")
    second = conversations.create_conversation("Other")
    history.append_message(
        conversation_id=first.id,
        role="user",
        content="Show parks near Rome and keep the original place name.",
    )
    history.append_message(
        conversation_id=first.id,
        role="assistant",
        content="Rome parks are ready.",
    )
    history.append_message(
        conversation_id=first.id,
        role="user",
        content="Now compare Rome flood observations.",
    )
    history.append_message(
        conversation_id=second.id,
        role="user",
        content="Rome must not leak across conversations.",
    )

    page = history.search_conversation_history(
        first.id,
        "rome",
        limit=1,
    )
    assert [item["turn_index"] for item in page["messages"]] == [1]
    assert page["pagination"]["next_cursor"] == "1"
    assert page["messages"][0]["excerpt"].startswith("Show parks")

    second_page = history.search_conversation_history(
        first.id,
        "rome",
        cursor=page["next_cursor"],
        limit=10,
    )
    assert [item["turn_index"] for item in second_page["messages"]] == [2, 3]
    assert all(item["conversation_id"] == first.id for item in second_page["messages"])

    before_current = history.search_conversation_history(
        first.id,
        "rome",
        before_turn_index=3,
        limit=10,
    )
    assert [item["turn_index"] for item in before_current["messages"]] == [1, 2]


def test_conversation_page_searches_original_messages_and_uses_keyset_cursor() -> None:
    backend = _backend()
    conversations = ConversationRepository(backend)
    history = ChatHistoryRepository(backend)
    first = conversations.create_conversation("First")
    second = conversations.create_conversation("Second")
    third = conversations.create_conversation("Third")
    history.append_message(
        conversation_id=second.id,
        role="user",
        content="A unique hydrograph request",
    )

    page = conversations.list_conversation_page(limit=2)
    assert len(page["conversations"]) == 2
    assert page["pagination"]["next_cursor"]
    next_page = conversations.list_conversation_page(
        cursor=page["pagination"]["next_cursor"],
        limit=2,
    )
    listed = [item["conversation_id"] for item in page["conversations"]]
    listed.extend(item["conversation_id"] for item in next_page["conversations"])
    assert set(listed) == {first.id, second.id, third.id}

    searched = conversations.search_conversations("hydrograph")
    assert [item["conversation_id"] for item in searched["conversations"]] == [
        second.id
    ]


def test_run_trace_is_paged_and_redacts_secrets_and_reasoning() -> None:
    backend = _backend()
    conversations = ConversationRepository(backend)
    runs = AgentRunRepository(backend)
    events = AgentRunEventRepository(backend)
    conversation = conversations.create_conversation("Trace")
    run = runs.create_run(conversation.id, "trace request", "trace request")
    events.append_event(
        RunEventCreate(
            conversation_id=conversation.id,
            run_id=run.run_id,
            run_version=1,
            type=RunEventType.TRACE,
            visibility=RunEventVisibility.INTERNAL,
            payload={
                "kind": "tool_result",
                "tool": "search",
                "api_key": "must-not-leak",
                "nested": {"reasoning": "hidden text", "count": 2},
            },
        )
    )
    events.append_event(
        RunEventCreate(
            conversation_id=conversation.id,
            run_id=run.run_id,
            run_version=1,
            type=RunEventType.PROGRESS,
            payload={"stage": "completed"},
        )
    )

    page = runs.read_trace(conversation.id, run.run_id, limit=1)
    assert len(page["events"]) == 1
    assert page["pagination"]["next_cursor"] == "1"
    payload = page["events"][0]["payload"]
    assert payload["kind"] == "tool_result"
    assert "api_key" not in payload
    assert "reasoning" not in payload["nested"]
    assert page["events"][0]["kind"] == "tool_result"

    remaining = runs.get_run_trace(
        conversation.id,
        run.run_id,
        cursor=page["pagination"]["next_cursor"],
        limit=10,
    )
    assert [event["sequence"] for event in remaining["events"]] == [2]


def test_run_summary_page_supports_request_search() -> None:
    backend = _backend()
    conversations = ConversationRepository(backend)
    runs = AgentRunRepository(backend)
    conversation = conversations.create_conversation("Runs")
    runs.create_run(conversation.id, "find rivers", "find rivers")
    page = runs.list_run_summaries(conversation.id, query="rivers")
    assert len(page["runs"]) == 1
    assert page["runs"][0]["original_request"] == "find rivers"
