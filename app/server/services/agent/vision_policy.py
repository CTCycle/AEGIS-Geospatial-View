from __future__ import annotations

from typing import Any

from server.domain.agent.vision_policy import (
    MAP_INSPECTION_TOOL_NAMES,
    MAP_VALIDATION_ERROR_TYPES,
    VisionPolicy,
    VisionState,
    capture_ref_for,
)

# Model-step call kinds that can carry a vision attachment.  The routing call
# bypasses ``_model_step`` entirely and is therefore never eligible.
ITERATION_CALL_KIND = "iteration"
TERMINAL_CALL_KIND = "terminal"

_TERMINAL_CALL_KINDS = frozenset({TERMINAL_CALL_KIND})


###############################################################################
class VisionPolicyEngine:
    """Deterministic vision-attachment decisions for the native agent loop.

    The engine never mutates retry counts or budgets.  It only decides when a
    captured map image may be attached to the next model call, and vision
    degrades cleanly (no image) whenever the capture or capability is missing.
    """

    def __init__(
        self,
        *,
        policy: str,
        vision_supported: bool | None,
        max_vision_calls: int = 2,
    ) -> None:
        self.policy = policy
        self.vision_supported = vision_supported is True
        self.max_vision_calls = max(1, int(max_vision_calls))

    # -------------------------------------------------------------------------
    @property
    def policy_enum(self) -> VisionPolicy:
        return VisionPolicy(self.policy)

    # -------------------------------------------------------------------------
    @staticmethod
    def meaningful_map_rendered(state: Any) -> bool:
        """True when a meaningful map has been rendered for this run."""

        if state.render_verified:
            return True
        if state.prepared_map_session is None:
            return False
        if state.render_observations and state.render_observations[-1].status == "ready":
            return True
        return False

    # -------------------------------------------------------------------------
    @staticmethod
    def relevant_failures(state: Any) -> int:
        """Derived count of map-generation/understanding/validation failures."""

        render_failures = sum(
            1
            for observation in state.render_observations
            if observation.status == "failed"
        )
        tool_failures = 0
        for result in state.tool_results:
            if result.status != "failed":
                continue
            error = result.error
            error_type = str(error.error_type) if error is not None else ""
            if result.tool_name in MAP_INSPECTION_TOOL_NAMES or (
                error_type in MAP_VALIDATION_ERROR_TYPES
            ):
                tool_failures += 1
        return render_failures + tool_failures

    # -------------------------------------------------------------------------
    def current_capture_ref(self, state: Any) -> str | None:
        """Identity of the latest render that may have produced a capture."""

        for observation in reversed(state.render_observations):
            if observation.status == "ready":
                return capture_ref_for(
                    observation.map_session_id,
                    observation.collection_revision,
                )
        prepared = state.prepared_map_session
        if prepared is not None:
            session_id = getattr(prepared, "session_id", None)
            collection = getattr(prepared, "overlay_collection", None)
            revision = getattr(collection, "revision", None)
            if session_id and isinstance(revision, int):
                return capture_ref_for(session_id, revision)
        return None

    # -------------------------------------------------------------------------
    def should_capture(self, state: Any) -> bool:
        """Whether the render handshake should request a browser capture."""

        if not self.vision_supported or self.policy_enum == VisionPolicy.DISABLED:
            return False
        if not self.meaningful_map_rendered(state):
            return False
        vision_state = state.vision_state
        if vision_state is not None and vision_state.vision_calls >= self.max_vision_calls:
            return False
        if self.policy_enum == VisionPolicy.ON_FAILURE:
            return self.relevant_failures(state) >= 1
        if self.policy_enum in {VisionPolicy.ALWAYS, VisionPolicy.FINAL_CHECK}:
            return True
        return False

    # -------------------------------------------------------------------------
    def should_attach(
        self,
        state: Any,
        *,
        capture_ref: str | None,
        capture_present: bool,
        call_kind: str,
    ) -> bool:
        """Whether the next ``_model_step`` should attach the captured image."""

        if not self.vision_supported or self.policy_enum == VisionPolicy.DISABLED:
            return False
        if not capture_present or not capture_ref:
            return False
        vision_state = state.vision_state
        if vision_state is not None:
            if vision_state.vision_calls >= self.max_vision_calls:
                return False
            if vision_state.attached_capture_ref == capture_ref:
                return False
        if self.policy_enum == VisionPolicy.ALWAYS:
            return True
        if self.policy_enum == VisionPolicy.ON_FAILURE:
            return self.relevant_failures(state) >= 1
        if self.policy_enum == VisionPolicy.FINAL_CHECK:
            return call_kind in _TERMINAL_CALL_KINDS
        return False

    # -------------------------------------------------------------------------
    def mark_attached(self, state: Any, *, capture_ref: str) -> None:
        """Record that the capture was attached (persisted in run state)."""

        current = state.vision_state
        if current is None:
            current = VisionState()
        state.vision_state = current.model_copy(
            update={
                "attached_capture_ref": capture_ref,
                "vision_calls": current.vision_calls + 1,
            }
        )