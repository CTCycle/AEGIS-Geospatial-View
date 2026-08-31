from __future__ import annotations

from server.common.typing import is_json_object
from pydantic import ValidationError

from server.contracts.geospatial import MapSession
from server.contracts.runs import (
    ActiveConversationRunSnapshot,
    ConversationMessageSnapshot,
    ConversationSnapshotResponse,
)
from server.domain.agent.pipeline import ConversationTaskSnapshot
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.conversations import ConversationRepository
from server.services.chat.history_service import ChatHistoryService


###############################################################################
class ConversationSnapshotContractError(RuntimeError):
    """Raised when durable conversation state is not current-contract data."""


###############################################################################
class ConversationSnapshotService:
    """Assemble the durable state needed to restore one conversation."""

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        conversation_repository: ConversationRepository,
        history_service: ChatHistoryService,
        run_repository: AgentRunRepository,
    ) -> None:
        self.conversation_repository = conversation_repository
        self.history_service = history_service
        self.run_repository = run_repository

    # -------------------------------------------------------------------------
    def get_snapshot(self, conversation_id: str) -> ConversationSnapshotResponse:
        record = self.conversation_repository.verify_conversation_access(
            conversation_id,
            None,
        )
        persisted = self.conversation_repository.read_state(conversation_id)
        try:
            task_snapshot = self._task_snapshot(persisted.get("task_snapshot"))
            map_session = self._map_session(task_snapshot)
            messages = [
                ConversationMessageSnapshot(
                    role=row["role"],
                    content=row["content"],
                    created_at=row["created_at"],
                )
                for row in self.history_service.list_messages(
                    conversation_id=conversation_id
                )
            ]
            raw_memory_snapshot: object = persisted.get("memory_snapshot") or {}
            if not is_json_object(raw_memory_snapshot):
                raise ValueError("memory_snapshot must be an object")
            memory_snapshot = raw_memory_snapshot
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise ConversationSnapshotContractError(
                "Stored conversation state does not match the current contract."
            ) from exc

        active_run = self.run_repository.get_active_run_for_conversation(
            conversation_id
        )
        return ConversationSnapshotResponse(
            conversation_id=record.id,
            title=record.title,
            context_revision=int(persisted["context_revision"]),
            messages=messages,
            task_snapshot=task_snapshot,
            memory_snapshot=memory_snapshot,
            map_session=map_session,
            active_run=(
                ActiveConversationRunSnapshot(
                    run_id=active_run.run_id,
                    run_version=active_run.active_run_version,
                    state=active_run.state,
                )
                if active_run is not None
                else None
            ),
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _task_snapshot(value: object) -> ConversationTaskSnapshot | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("task_snapshot must be an object or null")
        return ConversationTaskSnapshot.model_validate(value)

    # -------------------------------------------------------------------------
    @staticmethod
    def _map_session(
        task_snapshot: ConversationTaskSnapshot | None,
    ) -> MapSession | None:
        if task_snapshot is None or task_snapshot.active_map_session is None:
            return None
        return MapSession.model_validate(task_snapshot.active_map_session)
