from __future__ import annotations

from types import SimpleNamespace

from server.domain.agent.vision_policy import VisionPolicy, VisionState
from server.services.agent.vision_policy import (
    ITERATION_CALL_KIND,
    TERMINAL_CALL_KIND,
    VisionPolicyEngine,
)


###############################################################################
def _state(
    *,
    render_verified: bool = True,
    ready_observation: bool = True,
    failed_observations: int = 0,
    failed_tools: int = 0,
    vision_state: VisionState | None = None,
    tool_names: tuple[str, ...] = ("apply_map_plan",),
) -> SimpleNamespace:
    render_observations = []
    if ready_observation:
        render_observations.append(
            SimpleNamespace(
                map_session_id="map-1",
                collection_revision=2,
                attempt=1,
                status="ready",
            )
        )
    for _ in range(failed_observations):
        render_observations.append(
            SimpleNamespace(
                map_session_id="map-1",
                collection_revision=1,
                attempt=1,
                status="failed",
            )
        )
    tool_results = []
    for _ in range(failed_tools):
        tool_results.append(
            SimpleNamespace(
                tool_name=tool_names[0],
                status="failed",
                error=SimpleNamespace(error_type="semantic_validation"),
            )
        )
    return SimpleNamespace(
        render_verified=render_verified,
        prepared_map_session=None,
        render_observations=render_observations,
        tool_results=tool_results,
        vision_state=vision_state,
    )


###############################################################################
def _engine(
    policy: str,
    *,
    vision_supported: bool | None = True,
    max_vision_calls: int = 2,
) -> VisionPolicyEngine:
    return VisionPolicyEngine(
        policy=policy,
        vision_supported=vision_supported,
        max_vision_calls=max_vision_calls,
    )


###############################################################################
def test_disabled_policy_never_captures_or_attaches() -> None:
    state = _state()
    engine = _engine(VisionPolicy.ALWAYS.value)
    # Vision absent (unsupported) must be treated as disabled regardless of
    # the configured policy.
    unsupported = _engine(VisionPolicy.ALWAYS.value, vision_supported=None)
    disabled = _engine(VisionPolicy.DISABLED.value)

    assert disabled.should_capture(state) is False
    assert disabled.should_attach(
        state, capture_ref="map-1:2", capture_present=True, call_kind=ITERATION_CALL_KIND
    ) is False
    assert unsupported.should_capture(state) is False
    assert unsupported.should_attach(
        state, capture_ref="map-1:2", capture_present=True, call_kind=ITERATION_CALL_KIND
    ) is False
    assert engine.should_capture(state) is True


###############################################################################
def test_always_policy_captures_and_attaches_once_per_render() -> None:
    state = _state()
    engine = _engine(VisionPolicy.ALWAYS.value)

    assert engine.should_capture(state) is True
    assert engine.should_attach(
        state, capture_ref="map-1:2", capture_present=True, call_kind=ITERATION_CALL_KIND
    ) is True

    # After one attachment, the same render is not attached again.
    engine.mark_attached(state, capture_ref="map-1:2")
    assert engine.should_attach(
        state, capture_ref="map-1:2", capture_present=True, call_kind=ITERATION_CALL_KIND
    ) is False
    # A different render (new collection revision) is eligible again.
    assert engine.should_attach(
        state, capture_ref="map-1:3", capture_present=True, call_kind=ITERATION_CALL_KIND
    ) is True


###############################################################################
def test_on_failure_policy_stays_inactive_until_a_relevant_failure() -> None:
    clean = _state(failed_observations=0, failed_tools=0)
    engine = _engine(VisionPolicy.ON_FAILURE.value)

    assert engine.should_capture(clean) is False
    assert engine.should_attach(
        clean, capture_ref="map-1:2", capture_present=True, call_kind=ITERATION_CALL_KIND
    ) is False
    assert engine.relevant_failures(clean) == 0

    failed_render = _state(failed_observations=1)
    assert engine.relevant_failures(failed_render) == 1
    assert engine.should_capture(failed_render) is True
    assert engine.should_attach(
        failed_render,
        capture_ref="map-1:2",
        capture_present=True,
        call_kind=ITERATION_CALL_KIND,
    ) is True

    failed_tool = _state(failed_tools=1)
    assert engine.relevant_failures(failed_tool) == 1
    assert engine.should_capture(failed_tool) is True


###############################################################################
def test_final_check_policy_attaches_only_on_terminal_calls() -> None:
    state = _state()
    engine = _engine(VisionPolicy.FINAL_CHECK.value)

    assert engine.should_capture(state) is True
    assert engine.should_attach(
        state, capture_ref="map-1:2", capture_present=True, call_kind=ITERATION_CALL_KIND
    ) is False
    assert engine.should_attach(
        state, capture_ref="map-1:2", capture_present=True, call_kind=TERMINAL_CALL_KIND
    ) is True


###############################################################################
def test_attach_requires_an_existing_capture_and_a_capture_ref() -> None:
    state = _state()
    engine = _engine(VisionPolicy.ALWAYS.value)

    assert engine.should_attach(
        state, capture_ref=None, capture_present=False, call_kind=ITERATION_CALL_KIND
    ) is False
    assert engine.should_attach(
        state, capture_ref="map-1:2", capture_present=False, call_kind=ITERATION_CALL_KIND
    ) is False


###############################################################################
def test_capture_ref_falls_back_to_prepared_map_session() -> None:
    state = SimpleNamespace(
        render_verified=False,
        prepared_map_session=SimpleNamespace(
            session_id="session-9",
            overlay_collection=SimpleNamespace(revision=4),
        ),
        render_observations=[],
        tool_results=[],
        vision_state=None,
    )
    engine = _engine(VisionPolicy.ALWAYS.value)
    assert engine.current_capture_ref(state) == "session-9:4"


###############################################################################
def test_vision_calls_cap_limits_further_attachments() -> None:
    state = _state(vision_state=VisionState(attached_capture_ref="map-1:1", vision_calls=2))
    engine = _engine(VisionPolicy.ALWAYS.value, max_vision_calls=2)

    assert engine.should_capture(state) is False
    assert engine.should_attach(
        state, capture_ref="map-1:2", capture_present=True, call_kind=ITERATION_CALL_KIND
    ) is False


###############################################################################
def test_mark_attached_persists_capture_ref_and_increments_vision_calls() -> None:
    state = _state(vision_state=None)
    engine = _engine(VisionPolicy.ALWAYS.value)
    assert state.vision_state is None

    engine.mark_attached(state, capture_ref="map-1:2")

    assert state.vision_state is not None
    assert state.vision_state.attached_capture_ref == "map-1:2"
    assert state.vision_state.vision_calls == 1