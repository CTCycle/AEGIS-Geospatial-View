from __future__ import annotations

from server.common.typing import is_json_object

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select, update

from server.domain.agent.conversation import ConversationState
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas.models import ChatMessageRecord, ConversationRecord

###############################################################################
class ChatHistoryRepository:
    """Persist and retrieve conversation messages.

    Message history is the canonical source for historical recall.  Search
    returns bounded excerpts from the original rows rather than searching a
    derived summary, and the conversation id is always part of the query so a
    model-facing caller cannot accidentally inspect another conversation.
    """

    MAX_SEARCH_LIMIT = 50
    MAX_QUERY_CHARS = 300
    MAX_EXCERPT_CHARS = 480

    # -------------------------------------------------------------------------
    def __init__(self, database: SQLiteRepository) -> None:
        self._session_factory = database.session

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_message_dict(row: ChatMessageRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "conversation_id": row.conversation_id,
            "turn_index": row.turn_index,
            "request_id": row.request_id,
            "role": row.role,
            "content": row.content,
            "structured_payload": row.structured_payload,
            "tool_payload": row.tool_payload,
            "map_session": row.map_session,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    # -------------------------------------------------------------------------
    def append_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        request_id: str | None = None,
        structured_payload: Any = None,
        tool_payload: Any = None,
        map_session: Any = None,
    ) -> ChatMessageRecord:
        with self._session_factory() as session:
            turn_index = session.scalar(
                update(ConversationRecord)
                .where(ConversationRecord.id == conversation_id)
                .values(
                    next_message_sequence=ConversationRecord.next_message_sequence + 1,
                    updated_at=datetime.now(UTC),
                )
                .returning(ConversationRecord.next_message_sequence)
            )
            if turn_index is None:
                raise ValueError("Conversation not found.")
            payload = self._with_request_id(structured_payload, request_id)
            message = ChatMessageRecord(
                conversation_id=conversation_id,
                turn_index=turn_index,
                request_id=request_id,
                role=role,
                content=content,
                structured_payload=payload,
                tool_payload=tool_payload,
                map_session=map_session,
            )
            session.add(message)
            session.commit()
            session.refresh(message)
            return message

    # -------------------------------------------------------------------------
    def append_assistant_message_with_state(
        self,
        *,
        conversation_id: str,
        expected_revision: int,
        conversation_state: dict[str, Any],
        content: str,
        request_id: str,
        structured_payload: Any = None,
        tool_payload: Any = None,
        map_session: Any = None,
    ) -> tuple[ChatMessageRecord, int]:
        """Commit the terminal assistant message and conversation state atomically."""

        next_revision = max(0, int(expected_revision) + 1)
        canonical_state = ConversationState.from_persisted(
            conversation_id,
            conversation_state,
            revision=next_revision,
        ).model_copy(update={"revision": next_revision})
        persisted_state = canonical_state.model_dump(mode="json")
        with self._session_factory() as session:
            row = session.execute(
                update(ConversationRecord)
                .where(
                    ConversationRecord.id == conversation_id,
                    ConversationRecord.context_revision == expected_revision,
                )
                .values(
                    context_revision=ConversationRecord.context_revision + 1,
                    conversation_state=persisted_state,
                    next_message_sequence=ConversationRecord.next_message_sequence + 1,
                    updated_at=datetime.now(UTC),
                )
                .returning(
                    ConversationRecord.next_message_sequence,
                    ConversationRecord.context_revision,
                )
            ).one_or_none()
            if row is None:
                raise ValueError("Conversation context revision conflict.")
            turn_index, revision = row
            existing = session.scalar(
                select(ChatMessageRecord).where(
                    ChatMessageRecord.conversation_id == conversation_id,
                    ChatMessageRecord.role == "assistant",
                    ChatMessageRecord.request_id == request_id,
                )
            )
            structured = self._with_request_id(structured_payload, request_id)
            existing_payload = (
                existing.structured_payload
                if existing is not None and is_json_object(existing.structured_payload)
                else {}
            )
            existing_status = str(
                existing_payload.get("presentation_status") or ""
            )
            if (
                existing is not None
                and existing_payload.get("native") is True
                and existing_status in {"prepared", "pending", "prepared_unverified"}
            ):
                # Suspended native runs first persist a provisional assistant
                # row.  Resumption updates that row in place so the durable
                # conversation contains one assistant turn per request.
                existing.content = content
                existing.structured_payload = structured
                existing.tool_payload = tool_payload
                existing.map_session = map_session
                session.commit()
                session.refresh(existing)
                return existing, int(revision)
            message = ChatMessageRecord(
                conversation_id=conversation_id,
                turn_index=turn_index,
                request_id=request_id,
                role="assistant",
                content=content,
                structured_payload=structured,
                tool_payload=tool_payload,
                map_session=map_session,
            )
            session.add(message)
            session.commit()
            session.refresh(message)
            return message, int(revision)

    # -------------------------------------------------------------------------
    @staticmethod
    def _with_request_id(structured_payload: Any, request_id: str | None) -> Any:
        if request_id is None:
            return structured_payload
        if structured_payload is None:
            return {"request_id": request_id}
        if is_json_object(structured_payload):
            payload = dict(structured_payload)
            payload.setdefault("request_id", request_id)
            return payload
        return structured_payload

    # -------------------------------------------------------------------------
    def _last_assistant_payload(self, conversation_id: str) -> dict[str, Any] | None:
        row = self.get_last_assistant_message(conversation_id)
        payload = row.get("structured_payload") if row else None
        return payload if is_json_object(payload) else None

    # -------------------------------------------------------------------------
    def list_recent_messages(
        self, conversation_id: str, limit: int
    ) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            statement = (
                select(ChatMessageRecord)
                .where(ChatMessageRecord.conversation_id == conversation_id)
                .order_by(ChatMessageRecord.turn_index.desc())
                .limit(max(1, limit))
            )
            rows = list(reversed(session.execute(statement).scalars().all()))
        return [self._to_message_dict(row) for row in rows]

    # -------------------------------------------------------------------------
    def get_last_assistant_message(self, conversation_id: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = (
                session.execute(
                    select(ChatMessageRecord)
                    .where(
                        ChatMessageRecord.conversation_id == conversation_id,
                        ChatMessageRecord.role == "assistant",
                    )
                    .order_by(desc(ChatMessageRecord.turn_index))
                    .limit(1)
                )
                .scalars()
                .first()
            )
        return self._to_message_dict(row) if row is not None else None

    # -------------------------------------------------------------------------
    def find_message_by_request_id(
        self, *, conversation_id: str, role: str, request_id: str
    ) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = (
                session.execute(
                    select(ChatMessageRecord).where(
                        ChatMessageRecord.conversation_id == conversation_id,
                        ChatMessageRecord.role == role,
                        ChatMessageRecord.request_id == request_id,
                    )
                )
                .scalars()
                .first()
            )
        return self._to_message_dict(row) if row is not None else None

    # -------------------------------------------------------------------------
    def list_messages(self, *, conversation_id: str) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = (
                session.execute(
                    select(ChatMessageRecord)
                    .where(ChatMessageRecord.conversation_id == conversation_id)
                    .order_by(ChatMessageRecord.turn_index.asc())
                )
                .scalars()
                .all()
            )
        return [self._to_message_dict(row) for row in rows]

    # -------------------------------------------------------------------------
    def search_conversation_history(
        self,
        conversation_id: str,
        query: str,
        *,
        before_turn_index: int | None = None,
        cursor: str | None = None,
        limit: int = 8,
        excerpt_chars: int = MAX_EXCERPT_CHARS,
    ) -> dict[str, Any]:
        """Search original messages in one conversation.

        The result is a JSON-ready page with the following shape::

            {
                "messages": [
                    {
                        "id": 12,
                        "role": "user",
                        "turn_index": 4,
                        "created_at": "...+00:00",
                        "excerpt": "...matching original text...",
                    }
                ],
                "pagination": {
                    "cursor": "0",
                    "next_cursor": "1",
                    "has_more": True,
                    "total": 3,
                },
            }

        ``cursor`` is an opaque offset returned by this method.  An integer
        cursor is accepted as a convenience for callers that persist cursors
        as strings.  ``before_turn_index`` is exclusive, which lets a caller
        search only material that predates the current turn.
        """

        normalized_conversation_id = str(conversation_id).strip()
        if not normalized_conversation_id:
            raise ValueError("Conversation id is required.")
        normalized_query = " ".join(str(query).split())
        if not normalized_query:
            return self._empty_search_page(cursor=cursor, limit=limit)
        if len(normalized_query) > self.MAX_QUERY_CHARS:
            normalized_query = normalized_query[: self.MAX_QUERY_CHARS]
        if before_turn_index is not None and before_turn_index < 0:
            raise ValueError("before_turn_index must be non-negative.")

        bounded_limit = max(1, min(int(limit), self.MAX_SEARCH_LIMIT))
        bounded_excerpt = max(80, min(int(excerpt_chars), 2_000))
        offset = _parse_offset_cursor(cursor)
        pattern = _sqlite_contains_pattern(normalized_query)

        with self._session_factory() as session:
            if session.get(ConversationRecord, normalized_conversation_id) is None:
                raise ValueError("Conversation not found.")
            statement = select(ChatMessageRecord).where(
                ChatMessageRecord.conversation_id == normalized_conversation_id,
                func.lower(ChatMessageRecord.content).like(pattern, escape="\\"),
            )
            if before_turn_index is not None:
                statement = statement.where(
                    ChatMessageRecord.turn_index < before_turn_index
                )
            # Message sequence is unique per conversation.  Keep the id in
            # the order as a deterministic tie breaker for old/imported data.
            statement = statement.order_by(
                ChatMessageRecord.turn_index.asc(), ChatMessageRecord.id.asc()
            )
            rows = list(session.execute(statement).scalars().all())

        total = len(rows)
        page_rows = rows[offset : offset + bounded_limit]
        next_offset = offset + len(page_rows)
        next_cursor = str(next_offset) if next_offset < total else None
        matches = [
            self._to_history_match(row, normalized_query, bounded_excerpt)
            for row in page_rows
        ]
        pagination = {
            "cursor": str(offset) if offset else None,
            "next_cursor": next_cursor,
            "has_more": next_cursor is not None,
            "total": total,
            "limit": bounded_limit,
            "before_turn_index": before_turn_index,
        }
        return {
            "messages": matches,
            "pagination": pagination,
            # These top-level aliases make the page convenient for thin API
            # adapters while keeping ``pagination`` the canonical shape.
            "next_cursor": next_cursor,
            "has_more": next_cursor is not None,
            "total": total,
        }

    # -------------------------------------------------------------------------
    def search_messages(
        self,
        *,
        conversation_id: str,
        query: str,
        before_turn_index: int | None = None,
        cursor: str | None = None,
        limit: int = 8,
        excerpt_chars: int = MAX_EXCERPT_CHARS,
    ) -> dict[str, Any]:
        """Compatibility spelling for repository/API adapters."""

        return self.search_conversation_history(
            conversation_id,
            query,
            before_turn_index=before_turn_index,
            cursor=cursor,
            limit=limit,
            excerpt_chars=excerpt_chars,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_history_match(
        row: ChatMessageRecord, query: str, excerpt_chars: int
    ) -> dict[str, Any]:
        content = row.content or ""
        excerpt = _message_excerpt(content, query, excerpt_chars)
        return {
            "id": row.id,
            "conversation_id": row.conversation_id,
            "role": row.role,
            "turn_index": row.turn_index,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "excerpt": excerpt,
        }

    # -------------------------------------------------------------------------
    @classmethod
    def _empty_search_page(
        cls, *, cursor: str | None, limit: int
    ) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit), cls.MAX_SEARCH_LIMIT))
        pagination = {
            "cursor": cursor,
            "next_cursor": None,
            "has_more": False,
            "total": 0,
            "limit": bounded_limit,
            "before_turn_index": None,
        }
        return {
            "messages": [],
            "pagination": pagination,
            "next_cursor": None,
            "has_more": False,
            "total": 0,
        }

###############################################################################
def _sqlite_contains_pattern(value: str) -> str:
    """Build a case-insensitive SQLite LIKE pattern with escaped wildcards."""

    escaped = value.casefold().replace("\\", "\\\\")
    escaped = escaped.replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"

###############################################################################
def _parse_offset_cursor(cursor: str | None) -> int:
    if cursor is None or not str(cursor).strip():
        return 0
    value = str(cursor).strip()
    if not value.isdigit():
        raise ValueError("Invalid history cursor.")
    return max(0, int(value))

###############################################################################
def _message_excerpt(content: str, query: str, limit: int) -> str:
    """Return an original-text excerpt centered on the first match."""

    if len(content) <= limit:
        return content
    folded_content = content.casefold()
    match_at = folded_content.find(query.casefold())
    if match_at < 0:
        return f"{content[: max(0, limit - 1)].rstrip()}…"
    prefix = max(0, (limit - len(query) - 2) // 2)
    start = max(0, match_at - prefix)
    end = min(len(content), start + limit)
    if end - start < limit:
        start = max(0, end - limit)
    excerpt = content[start:end]
    if start > 0:
        excerpt = f"…{excerpt[1:] if excerpt.startswith('…') else excerpt}"
    if end < len(content):
        excerpt = f"{excerpt.rstrip('…')}…"
    return excerpt[:limit]
