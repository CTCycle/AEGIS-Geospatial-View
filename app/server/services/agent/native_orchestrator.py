"""Application coordinator for the canonical native AEGIS harness.

This module is deliberately smaller than the historical parser/planner
orchestrator.  It owns the durable conversation boundary and delegates all
model-directed work to ``AgentLoop`` through ``AgentTurnRunner``.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from collections.abc import Awaitable, Mapping
from typing import Any, Callable, Generator
from uuid import uuid4

from server.common.typing import is_json_object
from server.contracts.chat import ChatTurnRequest, ChatTurnResponse
from server.domain.agent.context import ConversationDirective
from server.domain.agent.conversation import ConversationState
from server.domain.agent.capability_route import AgentRunState
from server.domain.agent.reliability import (
    COMPLEX_RUN_SECONDS,
    DEFAULT_STAGE_LIMITS,
    INITIAL_RUN_SECONDS,
    AgentExecutionBudget,
)
from server.repositories.conversations import ConversationRepository
from server.repositories.model_settings import ModelSettingsRepository
from server.services.agent.agent_loop import AgentLoop
from server.services.agent.context_assembler import AgentContextAssembler
from server.services.agent.instruction_state import ConversationInstructionService
from server.services.agent.native_v2_turn import (
    AgentTurnRequest,
    AgentTurnResponse,
    AgentTurnRunner,
)
from server.services.chat.history_service import ChatHistoryService
from server.services.llm.context_profile_resolver import ModelContextProfileResolver


###############################################################################
class NativeAgentOrchestrator:
    """Hydrate, run, and persist one canonical native agent turn."""

    def __init__(
        self,
        *,
        agent_turn_runner: AgentTurnRunner,
        settings_repo: ModelSettingsRepository,
        history_service: ChatHistoryService,
        conversation_repository: ConversationRepository,
        evidence_repository: Any | None = None,
        context_profile_resolver: ModelContextProfileResolver | None = None,
        execution_settings: Any | None = None,
        application_timezone: str = "UTC",
        agent_loop: AgentLoop | None = None,
    ) -> None:
        self.agent_turn_runner = agent_turn_runner
        self.settings_repo = settings_repo
        self.history_service = history_service
        self.conversation_repository = conversation_repository
        self.evidence_repository = evidence_repository
        self.context_profile_resolver = context_profile_resolver
        self.execution_settings = execution_settings
        self.application_timezone = application_timezone
        self.agent_loop = agent_loop
        self.policy_engine = (
            getattr(agent_loop.tool_executor, "policy_engine", None)
            if agent_loop is not None
            else None
        )
        self.tool_registry = (
            getattr(agent_loop.tool_executor, "tool_registry", None)
            if agent_loop is not None
            else None
        )
        self.instruction_state_service = ConversationInstructionService()
        self.context_assembler = AgentContextAssembler(context_profile_resolver)
        self._conversation_locks: dict[str, asyncio.Lock] = {}

    # -------------------------------------------------------------------------
    async def run_turn(
        self,
        payload: ChatTurnRequest,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
        *,
        defer_map_commit: bool = False,
        agent_run_id: str | None = None,
        agent_run_version: int = 1,
        checkpoint: Mapping[str, Any] | None = None,
        checkpoint_callback: Callable[[AgentRunState], Awaitable[None]] | None = None,
        run_state_check: Callable[[], str | None] | None = None,
    ) -> ChatTurnResponse:
        lock = self._conversation_locks.setdefault(
            payload.conversation_id, asyncio.Lock()
        )
        async with lock:
            return await self._run_serialized(
                payload,
                progress_callback,
                defer_map_commit=defer_map_commit,
                agent_run_id=agent_run_id,
                agent_run_version=agent_run_version,
                checkpoint=checkpoint,
                checkpoint_callback=checkpoint_callback,
                run_state_check=run_state_check,
            )

    # -------------------------------------------------------------------------
    async def _run_serialized(
        self,
        payload: ChatTurnRequest,
        progress_callback: Callable[[str, dict[str, Any]], None] | None,
        *,
        defer_map_commit: bool,
        agent_run_id: str | None,
        agent_run_version: int,
        checkpoint: Mapping[str, Any] | None,
        checkpoint_callback: Callable[[AgentRunState], Awaitable[None]] | None,
        run_state_check: Callable[[], str | None] | None,
    ) -> ChatTurnResponse:
        self._ensure_current(run_state_check)
        request_id = payload.request_id or f"chat-{uuid4().hex[:12]}"
        conversation_id = payload.conversation_id
        settings = self.settings_repo.get_required()
        budget = self._new_execution_budget()
        persisted = self.conversation_repository.read_state(conversation_id)
        conversation_state = ConversationState.from_persisted(
            conversation_id,
            persisted.get("conversation_state"),
            revision=int(persisted.get("context_revision") or 0),
        )
        directives = [
            ConversationDirective.model_validate(item)
            for item in conversation_state.active_directives
        ]
        recent_count = len(
            self.history_service.list_recent_messages(
                conversation_id,
                limit=10_000,
            )
        )
        directives = self.instruction_state_service.apply_user_message(
            directives,
            payload.message,
            recent_count + 1,
        )
        existing = self._load_existing_response(
            self.history_service, conversation_id, request_id
        )
        if existing is not None:
            return existing
        if (
            self.history_service.find_message_by_request_id(
                conversation_id=conversation_id,
                role="user",
                request_id=request_id,
            )
            is None
        ):
            self.history_service.append_message(
                conversation_id=conversation_id,
                role="user",
                content=payload.message,
                request_id=request_id,
            )

        recent_messages = self.history_service.list_recent_messages(
            conversation_id,
            limit=200,
        )
        self._remove_current_user_message(recent_messages, payload.message)
        latest_memory = conversation_state.memory_projection()
        active_map = conversation_state.committed_map_session
        if active_map is not None:
            latest_memory["active_visualization"] = active_map.model_dump(mode="json")
            latest_memory["active_location"] = active_map.resolved_location.model_dump(
                mode="json"
            )

        relevant_outcomes = self._evidence_summaries(conversation_id)
        with self._stage(
            budget,
            "context_assembly",
            progress_callback,
            request_id=request_id,
            conversation_id=conversation_id,
        ):
            context_package = self.context_assembler.assemble(
                provider=settings.agent_model_provider,
                model=settings.agent_model_name,
                current_user_message=payload.message,
                messages=recent_messages,
                directives=self.instruction_state_service.active(directives),
                task_state=conversation_state.model_dump(mode="json"),
                map_memory=latest_memory,
                prior_summary=conversation_state.summary,
                relevant_tool_outcomes=relevant_outcomes,
                policy_constraints=dict(conversation_state.constraints),
                phase="native_loop",
            )
        budget.record_context_allocation(context_package.context_allocation)
        self._ensure_current(run_state_check)

        native_response = await self.agent_turn_runner.run(
            AgentTurnRequest(
                request_id=request_id,
                run_id=agent_run_id,
                run_version=agent_run_version,
                conversation_revision=int(persisted.get("context_revision") or 0),
                conversation_id=conversation_id,
                user_message=payload.message,
                provider=settings.agent_model_provider,
                model=settings.agent_model_name,
                budget=budget,
                messages=[
                    *context_package.recent_messages,
                    {"role": "user", "content": payload.message},
                ],
                context_package=context_package,
                active_map_session=active_map,
                location_refs=dict(conversation_state.resolved_locations),
                evidence_refs=[
                    str(item.get("evidence_id") or "")
                    for item in relevant_outcomes
                    if str(item.get("evidence_id") or "").strip()
                ],
                defer_map_commit=defer_map_commit,
                checkpoint=checkpoint,
                checkpoint_callback=checkpoint_callback,
                context_usage_callback=(
                    lambda usage: self._emit_context_usage(
                        progress_callback,
                        request_id=request_id,
                        conversation_id=conversation_id,
                        usage=usage,
                    )
                ),
                run_state_check=run_state_check,
            )
        )
        self._ensure_current(run_state_check)
        effective_defer = defer_map_commit
        committed_map = conversation_state.committed_map_session
        if not effective_defer and native_response.map_session is not None:
            committed_map = native_response.map_session
        merged_locations = dict(conversation_state.resolved_locations)
        merged_locations.update(native_response.location_refs)
        next_state = conversation_state.model_copy(
            update={
                "revision": int(persisted.get("context_revision") or 0) + 1,
                "active_directives": [
                    item.model_dump(mode="json") for item in directives
                ],
                "summary": context_package.summary,
                "summary_through_turn_index": context_package.summarized_through_turn_index,
                "goal": native_response.goal,
                "route": native_response.route,
                "constraints": _native_constraints(native_response),
                "resolved_locations": merged_locations,
                "evidence_refs": list(
                    dict.fromkeys(
                        [
                            *conversation_state.evidence_refs,
                            *[
                                ref
                                for item in native_response.tool_results
                                for ref in item.evidence_refs
                            ],
                        ]
                    )
                ),
                "committed_map_session": committed_map,
                "unresolved_questions": (
                    [native_response.operation.message]
                    if native_response.operation.kind == "clarification"
                    else []
                ),
            }
        )
        memory_snapshot = next_state.memory_projection()

        tool_payload = _native_tool_payload(native_response)
        execution_trace = dict(native_response.execution_trace or {})
        execution_trace["run_budget"] = budget.snapshot()
        execution_trace["context_usage_trace"] = list(
            native_response.execution_trace.get("context_usage_trace", [])
            if native_response.execution_trace
            else []
        )
        tool_payload["context_usages"] = list(execution_trace["context_usage_trace"])
        operation = native_response.operation
        response = ChatTurnResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            assistant_message=native_response.assistant_message,
            operation=operation,
            tool_payload=tool_payload,
            map_session=native_response.map_session,
            memory_snapshot=memory_snapshot,
            execution_trace=execution_trace,
            route=native_response.route,
            goal=native_response.goal,
            completion_contract=native_response.completion_contract,
            presentation_status=native_response.presentation_status,
            tool_results=native_response.tool_results,
            conversation_state=next_state,
        )
        with self._stage(
            budget,
            "persistence",
            progress_callback,
            request_id=request_id,
            conversation_id=conversation_id,
        ):
            revision = self.conversation_repository.write_state(
                conversation_id,
                expected_revision=int(persisted.get("context_revision") or 0),
                conversation_state=next_state.model_dump(mode="json"),
            )
            self.history_service.append_message(
                conversation_id=conversation_id,
                role="assistant",
                content=response.assistant_message,
                request_id=request_id,
                structured_payload={
                    "native": True,
                    "route": (
                        response.route.model_dump(mode="json")
                        if response.route is not None
                        else None
                    ),
                    "operation": operation.model_dump(mode="json"),
                    "goal": (
                        response.goal.model_dump(mode="json")
                        if response.goal is not None
                        else None
                    ),
                    "completion_contract": (
                        response.completion_contract.model_dump(mode="json")
                        if response.completion_contract is not None
                        else None
                    ),
                    "memory_snapshot": memory_snapshot,
                    "conversation_state": next_state.model_dump(mode="json"),
                    "execution_trace": execution_trace,
                    "presentation_status": response.presentation_status,
                    "tool_results": [
                        item.model_dump(mode="json") for item in response.tool_results
                    ],
                },
                tool_payload=tool_payload,
                map_session=None
                if effective_defer
                else (
                    native_response.map_session.model_dump(mode="json")
                    if native_response.map_session is not None
                    else None
                ),
            )
        if budget.terminal_reason is None:
            budget.terminal_reason = (
                "awaiting_render"
                if native_response.map_session is not None
                else "clarification_required"
                if operation.kind == "clarification"
                else "completed"
            )
        execution_trace["run_budget"] = budget.snapshot()
        execution_trace["context_revision"] = revision
        return response.model_copy(
            update={
                "context_revision": revision,
                "execution_trace": execution_trace,
            }
        )

    # -------------------------------------------------------------------------
    def _new_execution_budget(self) -> AgentExecutionBudget:
        configured = self.execution_settings
        stage_limits = dict(DEFAULT_STAGE_LIMITS)
        if configured is not None:
            stage_limits.update(
                {
                    "context_assembly": float(
                        getattr(configured, "context_assembly_seconds", 5.0)
                    ),
                    "route_request": float(
                        getattr(configured, "native_model_call_seconds", 60.0)
                    ),
                    "model_step": float(
                        getattr(configured, "native_model_call_seconds", 60.0)
                    ),
                    "tool_execution": float(
                        getattr(configured, "tool_absolute_seconds", 90.0)
                    ),
                    "map_assembly": float(
                        getattr(configured, "map_assembly_seconds", 20.0)
                    ),
                    "persistence": float(
                        getattr(configured, "persistence_seconds", 5.0)
                    ),
                }
            )
        return AgentExecutionBudget(
            total_seconds=float(
                getattr(configured, "initial_run_seconds", INITIAL_RUN_SECONDS)
                if configured is not None
                else INITIAL_RUN_SECONDS
            ),
            hard_max_seconds=float(
                getattr(configured, "complex_seconds", COMPLEX_RUN_SECONDS)
                if configured is not None
                else COMPLEX_RUN_SECONDS
            ),
            simple_run_seconds=float(
                getattr(configured, "simple_seconds", 150.0)
                if configured is not None
                else 150.0
            ),
            stage_limits=stage_limits,
        )

    # -------------------------------------------------------------------------
    def _evidence_summaries(self, conversation_id: str) -> list[dict[str, Any]]:
        if self.evidence_repository is None:
            return []
        try:
            values = self.evidence_repository.list_summaries(
                conversation_id,
                limit=100,
            )
        except Exception:
            return []
        result: list[dict[str, Any]] = []
        for item in values:
            if hasattr(item, "model_dump"):
                payload = item.model_dump(mode="json")
            elif isinstance(item, dict):
                payload = dict(item)
            else:
                continue
            result.append(payload)
        return result

    # -------------------------------------------------------------------------
    @staticmethod
    def _remove_current_user_message(
        messages: list[dict[str, Any]], message_text: str
    ) -> None:
        for index in range(len(messages) - 1, -1, -1):
            item = messages[index]
            if item.get("role") == "user" and item.get("content") == message_text:
                messages.pop(index)
                return

    # -------------------------------------------------------------------------
    @staticmethod
    def _load_existing_response(
        history_service: ChatHistoryService,
        conversation_id: str,
        request_id: str,
    ) -> ChatTurnResponse | None:
        existing = history_service.find_message_by_request_id(
            conversation_id=conversation_id,
            role="assistant",
            request_id=request_id,
        )
        if existing is None:
            return None
        payload = existing.get("structured_payload")
        if not isinstance(payload, dict) or not payload.get("native"):
            return None
        try:
            return ChatTurnResponse.model_validate(
                {
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "assistant_message": existing.get("content") or "",
                    "operation": payload.get("operation"),
                    "tool_payload": existing.get("tool_payload"),
                    "map_session": existing.get("map_session"),
                    "memory_snapshot": payload.get("memory_snapshot") or {},
                    "execution_trace": payload.get("execution_trace"),
                    "route": payload.get("route"),
                    "goal": payload.get("goal"),
                    "completion_contract": payload.get("completion_contract"),
                    "presentation_status": payload.get(
                        "presentation_status", "not_requested"
                    ),
                    "tool_results": payload.get("tool_results") or [],
                    "conversation_state": payload.get("conversation_state"),
                }
            )
        except Exception:
            return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _ensure_current(check: Callable[[], str | None] | None) -> None:
        if check is None:
            return
        value = str(check() or "").strip().casefold()
        if value in {"cancelled", "canceled", "cancel_requested"}:
            raise asyncio.CancelledError()
        if value in {"superseded", "superseded_by_steering", "stale"}:
            raise RuntimeError("Native run superseded by a newer conversation version.")

    # -------------------------------------------------------------------------
    @staticmethod
    def _emit_context_usage(
        callback: Callable[[str, dict[str, Any]], None] | None,
        *,
        request_id: str,
        conversation_id: str,
        usage: object,
    ) -> None:
        if callback is None or not is_json_object(usage):
            return
        try:
            callback(
                "context_usage",
                {
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "phase": "native_loop",
                    "context_usage": dict(usage),
                },
            )
        except Exception:
            return

    # -------------------------------------------------------------------------
    @staticmethod
    @contextmanager
    def _stage(
        budget: AgentExecutionBudget,
        stage: str,
        callback: Callable[[str, dict[str, Any]], None] | None,
        *,
        request_id: str,
        conversation_id: str,
    ) -> Generator[None, None, None]:
        if callback is not None:
            try:
                callback(
                    "stage",
                    {
                        "request_id": request_id,
                        "conversation_id": conversation_id,
                        "stage": stage,
                        "status": "started",
                        "remaining_deadline_ms": int(
                            budget.remaining_seconds() * 1000
                        ),
                    },
                )
            except Exception:
                pass
        with budget.observe(stage):
            yield


def _native_tool_payload(response: AgentTurnResponse) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for item in response.tool_results:
        content: dict[str, Any] = {
            "ok": item.status != "failed",
            "status": item.status,
            "summary": item.summary,
            "evidence_refs": list(item.evidence_refs),
            "map_candidate_id": item.map_candidate_id,
        }
        if item.error is not None:
            content["error"] = item.error.model_dump(mode="json")
        results.append(
            {
                "tool_call_id": item.call_id,
                "name": item.tool_name,
                "content": content,
                "is_error": item.status == "failed",
                "error": item.error.message if item.error is not None else None,
            }
        )
    return {
        "tool_results": results,
        "stopped_reason": (
            response.execution_trace.get("stopped_reason")
            if response.execution_trace
            else None
        ),
        "execution_trace": response.execution_trace,
    }


def _native_constraints(response: AgentTurnResponse) -> dict[str, Any]:
    """Persist only native route obligations needed by the next turn."""

    return {
        "completion_contract": (
            response.completion_contract.model_dump(mode="json")
            if response.completion_contract is not None
            else None
        ),
        "completion_requirements": list(
            response.completion_contract.requirements
            if response.completion_contract is not None
            else []
        ),
    }


__all__ = ["NativeAgentOrchestrator"]
