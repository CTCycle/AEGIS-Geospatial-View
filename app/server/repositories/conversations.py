from __future__ import annotations

import base64
import json

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, exists, func, or_, select, update

from server.domain.agent.conversation import ConversationState
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas.models import ChatMessageRecord, ConversationRecord

###############################################################################
class ConversationRepository:

    MAX_PAGE_LIMIT = 50
    MAX_QUERY_CHARS = 300

    # -------------------------------------------------------------------------
    def __init__(self, database: SQLiteRepository) -> None:
        self._session_factory = database.session

    # -------------------------------------------------------------------------
    def create_conversation(
        self, title: str | None, owner_user_id: str | None = None
    ) -> ConversationRecord:
        with self._session_factory() as session:
            conversation_id = f"conv_{uuid4().hex}"
            record = ConversationRecord(
                id=conversation_id,
                owner_user_id=owner_user_id,
                title=title.strip()
                if isinstance(title, str) and title.strip()
                else None,
                conversation_state=ConversationState.empty(
                    conversation_id, revision=1
                ).model_dump(mode="json"),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    # -------------------------------------------------------------------------
    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        with self._session_factory() as session:
            return session.get(ConversationRecord, conversation_id)

    # -------------------------------------------------------------------------
    def read_state(self, conversation_id: str) -> dict[str, Any]:
        record = self._require(conversation_id)
        return {
            "context_revision": record.context_revision,
            "conversation_state": record.conversation_state,
        }

    # -------------------------------------------------------------------------
    def write_state(
        self,
        conversation_id: str,
        *,
        expected_revision: int,
        conversation_state: dict[str, Any],
    ) -> int:
        values: dict[str, Any] = {
            "context_revision": ConversationRecord.context_revision + 1,
            "updated_at": datetime.now(UTC),
            "conversation_state": conversation_state,
        }
        with self._session_factory() as session:
            revision = session.scalar(
                update(ConversationRecord)
                .where(
                    ConversationRecord.id == conversation_id,
                    ConversationRecord.context_revision == expected_revision,
                )
                .values(**values)
                .returning(ConversationRecord.context_revision)
            )
            if revision is None:
                raise ValueError("Conversation context revision conflict.")
            session.commit()
            return int(revision)

    # -------------------------------------------------------------------------
    def verify_conversation_access(
        self, conversation_id: str, owner_user_id: str | None = None
    ) -> ConversationRecord:
        record = self._require(conversation_id)
        if record.owner_user_id is not None and record.owner_user_id != owner_user_id:
            raise PermissionError("Conversation access denied.")
        return record

    # -------------------------------------------------------------------------
    def list_conversations(self) -> list[ConversationRecord]:
        with self._session_factory() as session:
            return list(session.execute(select(ConversationRecord)).scalars().all())

    # -------------------------------------------------------------------------
    def list_conversation_page(
        self,
        *,
        query: str | None = None,
        owner_user_id: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return a deterministic, bounded page of conversation summaries.

        The page is ordered newest-first by ``updated_at`` and then by the
        conversation id.  The cursor contains the last returned sort key and
        is opaque to API callers.  A query matches the title or any original
        chat-message content; no derived summary is used for search.

        When ``owner_user_id`` is ``None`` only unowned conversations are
        returned.  This mirrors :meth:`verify_conversation_access` and keeps a
        listing endpoint from exposing an owned conversation to an anonymous
        caller.  Pass an explicit owner id to list that user's conversations.
        """

        bounded_limit = max(1, min(int(limit), self.MAX_PAGE_LIMIT))
        normalized_query = " ".join(str(query or "").split())
        if len(normalized_query) > self.MAX_QUERY_CHARS:
            normalized_query = normalized_query[: self.MAX_QUERY_CHARS]
        sort_cursor = _decode_conversation_cursor(cursor)

        with self._session_factory() as session:
            base_filters = self._conversation_filters(
                normalized_query=normalized_query,
                owner_user_id=owner_user_id,
                sort_cursor=None,
            )
            total = int(
                session.scalar(
                    select(func.count())
                    .select_from(ConversationRecord)
                    .where(*base_filters)
                )
                or 0
            )
            filters = list(base_filters)
            if sort_cursor is not None:
                cursor_time, cursor_id = sort_cursor
                filters.append(
                    or_(
                        ConversationRecord.updated_at < cursor_time,
                        and_(
                            ConversationRecord.updated_at == cursor_time,
                            ConversationRecord.id < cursor_id,
                        ),
                    )
                )
            rows = list(
                session.scalars(
                    select(ConversationRecord)
                    .where(*filters)
                    .order_by(
                        ConversationRecord.updated_at.desc(),
                        ConversationRecord.id.desc(),
                    )
                    .limit(bounded_limit + 1)
                ).all()
            )
            page_ids = [row.id for row in rows[:bounded_limit]]
            latest_messages: dict[str, str] = {}
            if page_ids:
                message_rows = session.execute(
                    select(
                        ChatMessageRecord.conversation_id,
                        ChatMessageRecord.content,
                    )
                    .where(ChatMessageRecord.conversation_id.in_(page_ids))
                    .order_by(
                        ChatMessageRecord.conversation_id.asc(),
                        ChatMessageRecord.turn_index.desc(),
                    )
                ).all()
                for conversation_id, content in message_rows:
                    if conversation_id not in latest_messages:
                        latest_messages[conversation_id] = _preview(content)

        has_more = len(rows) > bounded_limit
        page_rows = rows[:bounded_limit]
        next_cursor = (
            _encode_conversation_cursor(page_rows[-1]) if has_more and page_rows else None
        )
        conversations = [
            self._to_summary(
                row,
                last_message_preview=latest_messages.get(row.id),
            )
            for row in page_rows
        ]
        pagination = {
            "cursor": cursor,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "total": total,
            "limit": bounded_limit,
        }
        return {
            "conversations": conversations,
            "pagination": pagination,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "total": total,
        }

    # -------------------------------------------------------------------------
    def list_conversations_page(
        self,
        *,
        query: str | None = None,
        owner_user_id: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Explicit plural alias used by API composition code."""

        return self.list_conversation_page(
            query=query,
            owner_user_id=owner_user_id,
            cursor=cursor,
            limit=limit,
        )

    # -------------------------------------------------------------------------
    def search_conversations(
        self,
        query: str,
        *,
        owner_user_id: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search conversation titles and original messages."""

        return self.list_conversation_page(
            query=query,
            owner_user_id=owner_user_id,
            cursor=cursor,
            limit=limit,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _to_summary(
        row: ConversationRecord,
        *,
        last_message_preview: str | None = None,
    ) -> dict[str, Any]:
        updated_at = row.updated_at.isoformat() if row.updated_at else None
        created_at = row.created_at.isoformat() if row.created_at else None
        return {
            "conversation_id": row.id,
            "id": row.id,
            "title": row.title,
            "owner_user_id": row.owner_user_id,
            "context_revision": int(row.context_revision),
            "message_count": int(row.next_message_sequence),
            "last_message_preview": last_message_preview,
            "created_at": created_at,
            "updated_at": updated_at,
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _conversation_filters(
        *,
        normalized_query: str,
        owner_user_id: str | None,
        sort_cursor: tuple[datetime, str] | None,
    ) -> list[Any]:
        filters: list[Any] = [
            ConversationRecord.owner_user_id == owner_user_id
            if owner_user_id is not None
            else ConversationRecord.owner_user_id.is_(None)
        ]
        if normalized_query:
            pattern = _sqlite_contains_pattern(normalized_query)
            message_match = exists(
                select(1).where(
                    ChatMessageRecord.conversation_id == ConversationRecord.id,
                    func.lower(ChatMessageRecord.content).like(pattern, escape="\\"),
                )
            )
            filters.append(
                or_(
                    func.lower(ConversationRecord.title).like(
                        pattern, escape="\\"
                    ),
                    message_match,
                )
            )
        if sort_cursor is not None:
            cursor_time, cursor_id = sort_cursor
            filters.append(
                or_(
                    ConversationRecord.updated_at < cursor_time,
                    and_(
                        ConversationRecord.updated_at == cursor_time,
                        ConversationRecord.id < cursor_id,
                    ),
                )
            )
        return filters

    # -------------------------------------------------------------------------
    def _require(self, conversation_id: str) -> ConversationRecord:
        record = self.get_conversation(conversation_id)
        if record is None:
            raise ValueError("Conversation not found.")
        return record


###############################################################################
def _sqlite_contains_pattern(value: str) -> str:
    escaped = value.casefold().replace("\\", "\\\\")
    escaped = escaped.replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


###############################################################################
def _preview(value: object, *, limit: int = 240) -> str:
    text_value = " ".join(str(value or "").split())
    return text_value if len(text_value) <= limit else f"{text_value[: limit - 1]}…"


###############################################################################
def _encode_conversation_cursor(row: ConversationRecord) -> str:
    timestamp = row.updated_at.isoformat() if row.updated_at else ""
    payload = json.dumps(
        {"updated_at": timestamp, "conversation_id": row.id},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


###############################################################################
def _decode_conversation_cursor(
    cursor: str | None,
) -> tuple[datetime, str] | None:
    if cursor is None or not str(cursor).strip():
        return None
    encoded = str(cursor).strip()
    # Cursors are opaque, but accepting the raw sort key is useful for simple
    # command-line/API clients and keeps malformed input a clear 400-level
    # validation error instead of silently restarting at page one.
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
        timestamp_value = str(payload.get("updated_at") or "")
        conversation_id = str(payload.get("conversation_id") or "").strip()
        timestamp = datetime.fromisoformat(timestamp_value)
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid conversation cursor.") from exc
    if not conversation_id:
        raise ValueError("Invalid conversation cursor.")
    # SQLite stores these DateTime values without a timezone.  Normalize an
    # aware client-supplied cursor to the same naive UTC representation.
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(UTC).replace(tzinfo=None)
    return timestamp, conversation_id
