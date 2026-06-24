from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from server.common.time import utc_now
from server.domain.agent.pipeline import (
    ConversationTaskRecord,
    ConversationTaskSnapshot,
    SpecialistGroup,
    TaskFailureDetail,
    TaskStatus,
)
from server.domain.extraction.models import TurnParseResult
from server.domain.geographics import MapSession

###############################################################################
@dataclass
class _ConversationState:
    sequence: int = 0
    tasks: list[ConversationTaskRecord] = field(default_factory=list)
    active_visualization: dict[str, Any] | None = None
    updated_at: datetime = field(default_factory=utc_now)

###############################################################################
class ConversationTaskStateService:

    # -------------------------------------------------------------------------
    def __init__(self, *, ttl: timedelta = timedelta(hours=6)) -> None:
        self.ttl = ttl
        self._states: dict[str, _ConversationState] = {}
        self._lock = threading.RLock()

    # -------------------------------------------------------------------------
    def snapshot(self, conversation_key: str) -> ConversationTaskSnapshot:
        with self._lock:
            state = self._get_state(conversation_key)
            current = next((task for task in reversed(state.tasks) if task.is_current), None)
            return ConversationTaskSnapshot(
                conversation_key=conversation_key,
                current_task_id=current.task_id if current else None,
                tasks=list(state.tasks),
                active_visualization=state.active_visualization,
            )

    # -------------------------------------------------------------------------
    def start_task(
        self,
        conversation_key: str,
        turn: TurnParseResult,
        specialist: SpecialistGroup,
    ) -> ConversationTaskRecord:
        with self._lock:
            state = self._get_state(conversation_key)
            parent = next((task for task in reversed(state.tasks) if task.is_current), None)
            for task in state.tasks:
                task.is_current = False
            state.sequence += 1
            location = turn.location_signals[0].model_dump(mode="json") if turn.location_signals else None
            task = ConversationTaskRecord(
                task_id=f"task-{state.sequence}",
                raw_user_text=turn.user_text,
                prompt_summary=turn.user_text[:240],
                normalized_description=turn.normalized_action.action_label,
                task_type=turn.task_class,
                intent=turn.normalized_action.action_id,
                relationship=turn.relationship,
                required_entities=[turn.entity_target] if turn.entity_target else [],
                geographic_scope=location,
                required_data_layers=list(turn.requested_layers),
                visualization_changes={
                    "basemap": turn.requested_basemap,
                    "frontend_update": turn.expected_frontend_update,
                },
                specialist=specialist,
                parent_task_id=(
                    parent.task_id
                    if parent is not None and turn.relationship in {"follow_up", "correction", "clarification"}
                    else None
                ),
            )
            state.tasks.append(task)
            state.updated_at = utc_now()
            return task

    # -------------------------------------------------------------------------
    def update_task(
        self,
        conversation_key: str,
        task_id: str,
        *,
        status: TaskStatus,
        progress_summary: str | None = None,
        blocking_ambiguity: str | None = None,
        failure: TaskFailureDetail | None = None,
        tool_plan=None,
        tool_result_refs: list[str] | None = None,
    ) -> ConversationTaskRecord:
        with self._lock:
            state = self._get_state(conversation_key)
            task = next(item for item in state.tasks if item.task_id == task_id)
            task.status = status
            task.progress_summary = progress_summary
            task.blocking_ambiguity = blocking_ambiguity
            task.failure = failure
            if tool_plan is not None:
                task.tool_plan = tool_plan
            if tool_result_refs is not None:
                task.tool_result_refs = list(tool_result_refs)
            task.updated_at = utc_now()
            state.updated_at = utc_now()
            return task

    # -------------------------------------------------------------------------
    def set_active_visualization(
        self,
        conversation_key: str,
        map_session: MapSession | None,
    ) -> None:
        if map_session is None:
            return
        with self._lock:
            state = self._get_state(conversation_key)
            state.active_visualization = map_session.model_dump(mode="json")
            state.updated_at = utc_now()

    # -------------------------------------------------------------------------
    def latest_failure(self, conversation_key: str) -> TaskFailureDetail | None:
        with self._lock:
            state = self._get_state(conversation_key)
            failed = next(
                (task for task in reversed(state.tasks) if task.failure is not None),
                None,
            )
            return failed.failure if failed else None

    # -------------------------------------------------------------------------
    def clear(self, conversation_key: str) -> None:
        with self._lock:
            self._states.pop(conversation_key, None)

    # -------------------------------------------------------------------------
    def _get_state(self, conversation_key: str) -> _ConversationState:
        now = utc_now()
        expired = [
            key
            for key, state in self._states.items()
            if now - state.updated_at > self.ttl
        ]
        for key in expired:
            self._states.pop(key, None)
        state = self._states.setdefault(conversation_key, _ConversationState())
        state.updated_at = now
        return state


TASK_STATE_SERVICE = ConversationTaskStateService()
