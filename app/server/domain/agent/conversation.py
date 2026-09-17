"""Durable conversation state for the native AEGIS harness.

The conversation is the long-lived source of truth.  A model context is a
short-lived projection of this state and an ``AgentRunState`` is the
checkpointable state for one execution.  Keeping this contract independent of
prior task/planner projections makes follow-up turns resumable without
reconstructing semantic state from a recent-message suffix.
"""

from __future__ import annotations

import re
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from server.contracts.geospatial import MapSession
from server.domain.agent.capability_route import AgentGoal, CapabilityRoute
from server.domain.agent.decision import ResolvedLocation


_CLARIFICATION_ACTION_MARKERS = re.compile(
    r"\b(?:add|change|display|find|focus|get|map|move|remove|show|switch|use|"
    r"weather|environment(?:al)?|traffic|earthquake|satellite|terrain|layer|"
    r"overlay|zoom|around|near)\b",
    re.IGNORECASE,
)
_CLARIFICATION_NON_ANSWER = re.compile(
    r"^(?:hello|hi|hey)(?: there)?[.!?]?$|"
    r"^(?:thanks?|thank you|ok(?:ay)?|sure|great|fine|no problem|"
    r"never mind|nevermind|not sure|i(?: do not| don't) know)[.!?]?$",
    re.IGNORECASE,
)


class PendingClarification(BaseModel):
    """A clarification tied to the request that produced it.

    The legacy ``unresolved_questions`` value is read only while hydrating
    pre-schema-v2 persisted state.  This record is the durable source of
    truth: status and source terms let a later turn consume the clarification
    without making it a global blocker for unrelated work.
    """

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1_000)
    source_turn_index: int = Field(default=0, ge=0)
    source_request_id: str | None = None
    scope: Literal["current_request"] = "current_request"
    scope_terms: list[str] = Field(default_factory=list, max_length=24)
    status: Literal["active", "deferred", "answered"] = "active"

    @classmethod
    def from_turn(
        cls,
        question: str,
        *,
        source_turn_index: int,
        source_request_id: str | None = None,
        source_text: str = "",
    ) -> "PendingClarification":
        terms = [
            token
            for token in re.findall(r"[a-z0-9]+", source_text.casefold())
            if len(token) >= 3
        ]
        return cls(
            question=question,
            source_turn_index=source_turn_index,
            source_request_id=source_request_id,
            scope_terms=list(dict.fromkeys(terms))[:24],
        )

    @classmethod
    def from_legacy(cls, question: str) -> "PendingClarification":
        return cls(question=question.strip(), source_turn_index=0)

    def applies_to(self, message: str) -> bool:
        """Return whether ``message`` is plausibly answering this question.

        New map/layer requests are deliberately treated as a new scope even
        when they mention one of the original place terms.  Short, non-action
        replies remain eligible answers (for example ``Illinois`` or ``the
        country``), while prose unrelated to the question does not become a
        sticky clarification blocker.
        """

        normalized = " ".join(message.strip().split())
        if self.status == "answered" or not normalized:
            return False
        if _CLARIFICATION_ACTION_MARKERS.search(normalized):
            return False
        if _CLARIFICATION_NON_ANSWER.fullmatch(normalized):
            return False
        if "?" in normalized or len(normalized.split()) > 16:
            return False
        return bool(re.findall(r"[a-z0-9]+", normalized.casefold()))


class ConversationState(BaseModel):
    """Revisioned, durable state shared by all turns in one conversation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    conversation_id: str
    revision: int = Field(default=0, ge=0)
    active_directives: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]]()
    )
    summary: dict[str, Any] | None = None
    summary_through_turn_index: int = Field(default=0, ge=0)
    goal: AgentGoal | None = None
    route: CapabilityRoute | None = None
    constraints: dict[str, Any] = Field(default_factory=lambda: dict[str, Any]())
    resolved_locations: dict[str, ResolvedLocation] = Field(
        default_factory=lambda: dict[str, ResolvedLocation]()
    )
    evidence_refs: list[str] = Field(default_factory=lambda: list[str]())
    committed_map_session: MapSession | None = None
    pending_clarification: PendingClarification | None = None

    @classmethod
    def empty(cls, conversation_id: str, *, revision: int = 0) -> "ConversationState":
        return cls(conversation_id=conversation_id, revision=max(0, revision))

    @classmethod
    def from_persisted(
        cls,
        conversation_id: str,
        payload: object,
        *,
        revision: int = 0,
    ) -> "ConversationState":
        """Hydrate one validated state, or create the initial empty state."""

        if payload is None:
            return cls.empty(conversation_id, revision=revision)
        if isinstance(payload, dict):
            raw_payload = cast(dict[str, Any], payload)
            migrated: dict[str, Any] = dict(raw_payload)
            schema_version = migrated.get("schema_version", 2)
            if type(schema_version) is not int or schema_version not in {1, 2}:
                raise ValueError(
                    "Unsupported conversation state schema version."
                )
            pending: Any = migrated.get("pending_clarification")
            if pending is None:
                legacy_questions_value: Any = migrated.get("unresolved_questions")
                if isinstance(legacy_questions_value, list):
                    legacy_questions: list[Any] = cast(
                        list[Any], legacy_questions_value
                    )
                    first = next(
                        (
                            str(item).strip()
                            for item in legacy_questions
                            if str(item).strip()
                        ),
                        "",
                    )
                    if first:
                        migrated["pending_clarification"] = (
                            PendingClarification.from_legacy(first).model_dump(
                                mode="json"
                            )
                        )
            migrated["schema_version"] = 2
            # The old key is a migration input only; never retain it in the
            # validated durable/public contract.
            migrated.pop("unresolved_questions", None)
            state = cls.model_validate(migrated)
        else:
            state = cls.model_validate(payload)
        if state.conversation_id != conversation_id:
            raise ValueError("Conversation state belongs to another conversation.")
        return state.model_copy(update={"revision": max(state.revision, revision)})

    def pending_clarification_for(
        self, message: str
    ) -> PendingClarification | None:
        """Project only a clarification relevant to the current user turn."""

        pending = self.pending_clarification
        if pending is None or not pending.applies_to(message):
            return None
        return pending.model_copy(update={"status": "active"})

    def clarification_after_turn(self, message: str) -> PendingClarification | None:
        """Advance the durable clarification record for one user turn.

        An unrelated turn clears the current blocking projection but keeps the
        record deferred for a possible later answer.  Once answered, the
        record is terminal and must not be reopened by later turns.
        """

        pending = self.pending_clarification
        if pending is None or pending.status == "answered":
            return pending
        return pending.model_copy(
            update={
                "status": "answered" if pending.applies_to(message) else "deferred"
            }
        )

    def context_projection(self, message: str) -> dict[str, Any]:
        """Return the model-visible state with clarification scope applied."""

        result = self.model_dump(mode="json")
        pending = self.pending_clarification_for(message)
        result["pending_clarification"] = (
            pending.model_dump(mode="json") if pending is not None else None
        )
        return result

    def memory_projection(self) -> dict[str, Any]:
        """Return the bounded presentation projection used by the UI."""

        result: dict[str, Any] = {}
        if self.resolved_locations:
            key = "active_location" if "active_location" in self.resolved_locations else next(
                iter(self.resolved_locations)
            )
            result["active_location"] = self.resolved_locations[key].model_dump(mode="json")
        if self.committed_map_session is not None:
            result["active_visualization"] = self.committed_map_session.model_dump(mode="json")
        return result


__all__ = ["ConversationState", "PendingClarification"]
