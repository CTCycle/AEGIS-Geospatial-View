"""Conversation task ledger: merging, reuse compatibility and map identity.

The ledger in ``ConversationState.tasks`` records the verified outcome of
each request obligation.  These pure functions decide how a run's outcomes
replace earlier entries, which entries a new goal may reuse, and when a map
candidate is the map the user already sees.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from server.common.typing import json_object
from server.contracts.geospatial import MapSession
from server.domain.agent.capability_route import (
    AgentGoal,
    AgentTemporalScope,
    ConversationTask,
    same_target,
)

LEDGER_LIMIT = 32
# Freshness of provider evidence whose manifest declares no cache TTL.
DEFAULT_FRESHNESS_SECONDS = 900
# Entries of the most recent request shown to the model before routing.
PROJECTED_TASK_LIMIT = 12
# Unfinished entries of earlier requests shown alongside them.
PROJECTED_OPEN_LIMIT = 4
UNRESOLVED_STATUSES = frozenset({"in_progress", "blocked", "failed"})

###############################################################################
def map_fingerprint(session: MapSession) -> str:
    """Hash what the user sees; session ids, timestamps and revisions excluded."""

    viewport = session.viewport
    content = {
        "basemap_id": session.basemap_id,
        "viewport": [
            round(viewport.center_latitude, 5),
            round(viewport.center_longitude, 5),
            round(viewport.radius_m, 1),
            [round(value, 5) for value in viewport.bbox or []],
        ],
        "payload": {key: value for key, value in session.payload.items() if key != "map_candidate"},
        "overlays": sorted(
            (item.model_dump(mode="json") for item in session.overlay_collection.instances),
            key=lambda item: str(item["instance_id"]),
        ),
    }
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

###############################################################################
def merge_ledger(
    tasks: list[ConversationTask], outcomes: list[ConversationTask]
) -> list[ConversationTask]:
    """Fold one run's outcomes into the ledger and bound it.

    An outcome replaces its own request's entry for the same task id, and a
    completed outcome replaces an earlier completed one; a failed or blocked
    attempt never erases a completed result.  Unfinished work of an earlier
    request that the outcome takes over is kept as superseded.  Past the
    limit superseded entries go first, then completed, then the oldest.
    """

    merged = list(tasks)
    for outcome in outcomes:
        kept: list[ConversationTask] = []
        record = True
        for item in merged:
            if not _replaces(outcome, item):
                kept.append(item)
            elif item.status == "completed":
                if item.task_id != outcome.task_id or outcome.status != "completed":
                    kept.append(item)
                    # A worse result of the same run is not recorded at all.
                    if item.task_id == outcome.task_id and item.source_request_id == outcome.source_request_id:
                        record = False
            elif item.source_request_id == outcome.source_request_id:
                # The same run redoing an obligation replaces only that entry.
                if item.task_id != outcome.task_id:
                    kept.append(item)
            elif item.status in UNRESOLVED_STATUSES:
                kept.append(item.model_copy(update={"status": "superseded"}))
            else:
                kept.append(item)
        merged = [*kept, outcome] if record else kept
    while len(merged) > LEDGER_LIMIT:
        evict = next(
            (position for position, item in enumerate(merged) if item.status == "superseded"),
            None,
        )
        if evict is None:
            evict = next(
                (position for position, item in enumerate(merged) if item.status == "completed"),
                0,
            )
        del merged[evict]
    return merged

###############################################################################
def complete_presentation(
    tasks: list[ConversationTask], session: MapSession, now: datetime
) -> list[ConversationTask]:
    """Complete the presentation tasks that prepared the map now committed."""

    fingerprint = map_fingerprint(session)
    return [
        item.model_copy(update={"status": "completed", "completed_at": now})
        if item.kind == "presentation"
        and item.status == "in_progress"
        and item.map_revision == fingerprint
        else item
        for item in tasks
    ]

###############################################################################
def freshness_seconds(manifest: Mapping[str, object] | None) -> int:
    """Evidence lifetime declared by a manifest cache policy, else the default.

    A positive ``ttlSeconds`` plus its stale-while-revalidate allowance is
    how long the source itself serves a result; a zero TTL only means the
    server does not cache (tiles), not that a result expires at once.
    """

    policy = json_object((manifest or {}).get("cachePolicy"))
    ttl = policy.get("ttlSeconds")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
        return DEFAULT_FRESHNESS_SECONDS
    stale = policy.get("staleWhileRevalidateSeconds")
    return ttl + (stale if isinstance(stale, int) and not isinstance(stale, bool) and stale > 0 else 0)

###############################################################################
def compatible_tasks(
    tasks: list[ConversationTask],
    goal: AgentGoal,
    *,
    freshness: Callable[[str | None], int],
    now: datetime,
) -> list[ConversationTask]:
    """Completed places and evidence the new goal may reuse.

    A place is kept only when the goal names it.  Evidence is kept only when
    it is fresh and its geography, variable, time window and filters all
    agree with the goal; anything else would carry an old request into the
    new one.
    """

    data_obligations = [item for item in goal.obligations if item.kind == "data" and item.required]
    variables = [item.variable for item in data_obligations if item.variable]

    def requested_scope(target: str | None) -> AgentTemporalScope | None:
        for item in data_obligations:
            if target is None or any(same_target(target, other) for other in item.target_ids):
                return item.temporal_scope
        try:
            scope = AgentTemporalScope.model_validate(goal.temporal_scope)
        except ValueError:
            return None
        return scope if scope.mode != "none" else None

    def compatible(task: ConversationTask) -> bool:
        if task.status != "completed":
            return False
        if task.kind == "location":
            return any(
                same_target(target, known) for target in task.target_ids for known in goal.target_ids
            )
        if task.kind != "data" or not task.evidence_refs or task.completed_at is None:
            return False
        ttl = freshness(task.capability_id)
        if now - task.completed_at > timedelta(seconds=ttl):
            return False
        if goal.target_ids and not (
            task.target_ids
            and all(any(same_target(target, known) for known in goal.target_ids) for target in task.target_ids)
        ):
            return False
        if variables and not any(_same_variable(task.variable, item) for item in variables):
            return False
        targets: list[str | None] = [*task.target_ids] or [None]
        if not all(
            same_window(task.temporal_scope, requested_scope(target), tolerance_seconds=ttl)
            for target in targets
        ):
            return False
        return not any(
            key in task.filters and task.filters[key] != value for key, value in goal.filters.items()
        )

    return [item for item in tasks if compatible(item)]

###############################################################################
def same_window(
    stored: AgentTemporalScope | None,
    requested: AgentTemporalScope | None,
    *,
    tolerance_seconds: int,
) -> bool:
    """Whether stored evidence answers the requested time window.

    A request without a time window inherits the stored one.  Otherwise the
    mode must match and each bound may drift by at most the evidence
    lifetime, the span over which the source returns the same result.
    """

    if requested is None or requested.mode == "none":
        return True
    if stored is None or stored.mode != requested.mode:
        return False
    for left, right in (
        (stored.start_time_iso, requested.start_time_iso),
        (stored.end_time_iso, requested.end_time_iso),
        (stored.reference_time_iso, requested.reference_time_iso),
    ):
        if left is None and right is None:
            continue
        if left is None or right is None:
            return False
        try:
            drift = abs(_instant(left) - _instant(right))
        except ValueError:
            return False
        if drift > timedelta(seconds=tolerance_seconds):
            return False
    return True

###############################################################################
def ledger_view(tasks: list[ConversationTask]) -> list[dict[str, object]]:
    """Compact pre-route projection of the ledger.

    Shows the latest request's entries, known places, and the most recent
    unfinished work of earlier requests (description, status, reason and
    targets only), so a follow-up can refer back to it.  Older evidence stays
    out of the model context; once the new goal is routed, only its
    compatible entries are offered for reuse.
    """

    latest = next((item.source_request_id for item in reversed(tasks)), None)
    current = [
        position
        for position, item in enumerate(tasks)
        if item.source_request_id == latest or (item.kind == "location" and item.status == "completed")
    ][-PROJECTED_TASK_LIMIT:]
    earlier_open = [
        position
        for position, item in enumerate(tasks)
        if item.source_request_id != latest and item.status in UNRESOLVED_STATUSES
    ][-PROJECTED_OPEN_LIMIT:]
    return [
        _open_view(tasks[position]) if position in earlier_open else _task_view(tasks[position])
        for position in sorted({*current, *earlier_open})
    ]

###############################################################################
def _open_view(task: ConversationTask) -> dict[str, object]:
    view: dict[str, object | None] = {
        "id": task.task_id,
        "description": task.description,
        "status": task.status,
        "reason": task.reason,
        "targets": task.target_ids,
    }
    return {key: value for key, value in view.items() if value}

###############################################################################
def _task_view(task: ConversationTask) -> dict[str, object]:
    scope = task.temporal_scope
    window = (
        " ".join(
            part
            for part in (scope.mode, scope.start_time_iso, scope.end_time_iso, scope.reference_time_iso)
            if part
        )
        if scope is not None and scope.mode != "none"
        else None
    )
    view: dict[str, object | None] = {
        "id": task.task_id,
        "status": task.status,
        "reason": task.reason,
        "targets": task.target_ids,
        "variable": task.variable,
        "capability_id": task.capability_id,
        "window": window,
        "filters": task.filters,
        "evidence_refs": task.evidence_refs,
    }
    return {key: value for key, value in view.items() if value}

###############################################################################
def _replaces(outcome: ConversationTask, item: ConversationTask) -> bool:
    """Whether ``outcome`` addresses the same obligation as ``item``."""

    if outcome.task_id == item.task_id:
        return True
    # Otherwise only a fully specified obligation: same kind, places and variable.
    if (
        outcome.kind != item.kind
        or not outcome.target_ids
        or len(outcome.target_ids) != len(item.target_ids)
        or outcome.variable is None
    ):
        return False
    return all(
        any(same_target(left, right) for right in item.target_ids) for left in outcome.target_ids
    ) and _same_variable(item.variable, outcome.variable)

###############################################################################
def _same_variable(left: str | None, right: str) -> bool:
    if left is None:
        return False
    left_terms = set(re.findall(r"[a-z0-9]+", left.casefold()))
    right_terms = set(re.findall(r"[a-z0-9]+", right.casefold()))
    return bool(left_terms and right_terms) and (left_terms <= right_terms or right_terms <= left_terms)

###############################################################################
def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


__all__ = [
    "DEFAULT_FRESHNESS_SECONDS",
    "LEDGER_LIMIT",
    "UNRESOLVED_STATUSES",
    "compatible_tasks",
    "complete_presentation",
    "freshness_seconds",
    "ledger_view",
    "map_fingerprint",
    "merge_ledger",
    "same_window",
]
