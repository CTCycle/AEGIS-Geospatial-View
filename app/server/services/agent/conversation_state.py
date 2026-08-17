from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, cast

from server.common.time import utc_now
from server.domain.agent.pipeline import (
    ConversationTaskRecord,
    ConversationTaskSnapshot,
    ToolPlan,
    SpecialistGroup,
    TaskFailureDetail,
    TaskStatus,
)
from server.domain.agent.runtime import (
    AgentGoal,
    AgentTask,
    AgentTaskStatus,
    AgentThreadState,
    GeospatialWorkingState,
    apply_steering_delta as apply_runtime_steering_delta,
    validate_task_graph,
)
from server.domain.extraction.models import TurnParseResult
from server.domain.geographics import MapSession

###############################################################################
@dataclass
class _ConversationState:
    sequence: int = 0
    tasks: list[ConversationTaskRecord] = field(default_factory=lambda: list[ConversationTaskRecord]())
    runtime_state: AgentThreadState | None = None
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
            return ConversationTaskSnapshot(
                conversation_key=conversation_key,
                current_task_id=runtime.active_task_id if (runtime := self._runtime_state(state, conversation_key)) else None,
                goal=runtime.goal,
                tasks=[task.model_copy(deep=True) for task in runtime.tasks],
                geospatial_state=runtime.geospatial_state.model_copy(deep=True),
                evidence_refs=list(runtime.evidence_refs),
                active_map_session=runtime.active_map_session,
                assumptions=list(runtime.assumptions),
                unresolved_questions=list(runtime.unresolved_questions),
                conversation_summary=runtime.conversation_summary,
            )

    # -------------------------------------------------------------------------
    def has_state(self, conversation_key: str) -> bool:
        with self._lock:
            state = self._states.get(conversation_key)
            return state is not None and state.runtime_state is not None

    # -------------------------------------------------------------------------
    def apply_steering_delta(self, conversation_key: str, delta: Any) -> ConversationTaskSnapshot:
        """Apply a safe steering mutation to the live v2 state in place."""

        with self._lock:
            state = self._get_state(conversation_key)
            runtime = self._runtime_state(state, conversation_key)
            apply_runtime_steering_delta(runtime, delta)
            state.updated_at = utc_now()
            return self.snapshot(conversation_key)

    # -------------------------------------------------------------------------
    def start_task(
        self,
        conversation_key: str,
        turn: TurnParseResult,
        specialist: SpecialistGroup,
    ) -> ConversationTaskRecord:
        with self._lock:
            state = self._get_state(conversation_key)
            runtime = self._runtime_state(state, conversation_key)
            state.sequence = max(
                state.sequence,
                max(
                    (
                        int(item.id.removeprefix("task-"))
                        for item in runtime.tasks
                        if item.id.removeprefix("task-").isdigit()
                    ),
                    default=0,
                ),
            )
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
            runtime.revision += 1
            runtime.active_task_id = task.task_id
            runtime.goal = AgentGoal(
                id=task.task_id,
                text=task.normalized_description or task.raw_user_text,
                revision=runtime.revision,
            )
            atomic_items = list(turn.atomic_tasks)
            planned_tasks: list[AgentTask] = []
            if atomic_items:
                generated_ids: list[str] = []
                for index, item in enumerate(atomic_items, start=1):
                    raw_id = str(item.get("id") or "").strip()
                    generated_id = task.task_id if index == 1 else f"{task.task_id}-a{index}"
                    generated_ids.append(raw_id or generated_id)
                for index, item in enumerate(atomic_items, start=1):
                    raw_id = str(item.get("id") or "").strip()
                    item_id = task.task_id if index == 1 else f"{task.task_id}-a{index}"
                    dependencies: list[str] = []
                    for dependency in item.get("depends_on", []):
                        dependency_text = str(dependency)
                        if dependency_text.isdigit():
                            dependency_index = int(dependency_text) - 1
                            if 0 <= dependency_index < len(generated_ids):
                                dependencies.append(
                                    task.task_id
                                    if dependency_index == 0
                                    else f"{task.task_id}-a{dependency_index + 1}"
                                )
                        elif dependency_text in generated_ids:
                            dependencies.append(
                                task.task_id
                                if generated_ids.index(dependency_text) == 0
                                else f"{task.task_id}-a{generated_ids.index(dependency_text) + 1}"
                            )
                    planned_tasks.append(
                        AgentTask(
                            id=item_id,
                            description=str(
                                item.get("description")
                                or item.get("task")
                                or task.normalized_description
                                or task.raw_user_text
                            ),
                            kind=str(item.get("kind") or task.task_type),
                            depends_on=dependencies,
                            required=bool(item.get("required", True)),
                            scope_revision=runtime.revision,
                        )
                    )
            else:
                planned_tasks.append(
                    AgentTask(
                        id=task.task_id,
                        description=task.normalized_description or task.raw_user_text,
                        kind=task.task_type,
                        required=True,
                        scope_revision=runtime.revision,
                    )
                )
            runtime.tasks.extend(planned_tasks)
            validate_task_graph(runtime.tasks)
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
        tool_plan: dict[str, Any] | None = None,
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
                task.tool_plan = ToolPlan.model_validate(tool_plan)
            if tool_result_refs is not None:
                task.tool_result_refs = list(tool_result_refs)
            task.updated_at = utc_now()
            runtime = self._runtime_state(state, conversation_key)
            runtime_task = next((item for item in runtime.tasks if item.id == task_id), None)
            if runtime_task is not None:
                runtime_status = cast(
                    AgentTaskStatus,
                    {
                    "routed": "pending",
                    "needs_clarification": "blocked",
                    }.get(status, status),
                )
                runtime_task.status = runtime_status
                runtime_task.attempt_count = max(runtime_task.attempt_count, 1 if status == "in_progress" else 0)
                if failure is not None:
                    runtime_task.last_failure = failure.model_dump(mode="json")
            runtime.revision += 1
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
            runtime = self._runtime_state(state, conversation_key)
            runtime.active_map_session = map_session.model_dump(mode="json")
            runtime.geospatial_state.renderable_refs = [
                str(map_session.session_id)
            ] if getattr(map_session, "session_id", None) else runtime.geospatial_state.renderable_refs
            runtime.revision += 1
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
    def hydrate(self, conversation_key: str, payload: dict[str, Any] | None) -> None:
        if not payload:
            return
        if payload.get("schema_version") != 2:
            raise ValueError("Only task snapshot schema_version=2 is supported.")
        snapshot = ConversationTaskSnapshot.model_validate(payload)
        validate_task_graph(snapshot.tasks)
        with self._lock:
            self._states[conversation_key] = _ConversationState(
                runtime_state=AgentThreadState(
                    conversation_id=conversation_key,
                    revision=0,
                    active_task_id=snapshot.current_task_id,
                    goal=snapshot.goal,
                    tasks=[task.model_copy(deep=True) for task in snapshot.tasks],
                    geospatial_state=snapshot.geospatial_state.model_copy(deep=True),
                    evidence_refs=list(snapshot.evidence_refs),
                    active_map_session=snapshot.active_map_session,
                    assumptions=list(snapshot.assumptions),
                    unresolved_questions=list(snapshot.unresolved_questions),
                    conversation_summary=snapshot.conversation_summary,
                ),
            )

    # -------------------------------------------------------------------------
    def serialize(self, conversation_key: str) -> dict[str, Any]:
        return self.snapshot(conversation_key).model_dump(mode="json")

    # -------------------------------------------------------------------------
    @staticmethod
    def _runtime_state(state: _ConversationState, conversation_key: str) -> AgentThreadState:
        if state.runtime_state is None:
            state.runtime_state = AgentThreadState(
                conversation_id=conversation_key,
                geospatial_state=GeospatialWorkingState(),
            )
        return state.runtime_state

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


