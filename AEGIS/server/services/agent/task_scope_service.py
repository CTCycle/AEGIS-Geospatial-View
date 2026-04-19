from __future__ import annotations

import re
from typing import Any

from AEGIS.server.domain.agent.task_scope import TaskScopeDecision
from AEGIS.server.domain.extraction.models import ExtractedIntent


###############################################################################
class TaskScopeService:
    REFERENTIAL_PATTERNS = (
        re.compile(
            r"\b(same place|same area|there|that area|that place|around it|nearby|same coordinates)\b",
            re.IGNORECASE,
        ),
    )
    NEW_TASK_PATTERNS = (
        re.compile(
            r"\b(new task|different place|switch (?:location|city|area)|instead)\b",
            re.IGNORECASE,
        ),
    )
    COORDINATE_RE = re.compile(
        r"[+-]?\d{1,2}(?:\.\d+)?\s*[, ]\s*[+-]?\d{1,3}(?:\.\d+)?"
    )
    ADDRESS_RE = re.compile(
        r"\b\d{1,5}\s+[a-z0-9][a-z0-9\s.'\-]{2,}\b|\b(?:via|street|road|avenue|piazza|square|blvd|boulevard)\b",
        re.IGNORECASE,
    )
    CITY_OR_COUNTRY_RE = re.compile(
        r"\b(?:in|at|near)\s+[A-Z][a-z]+(?:[\s,]+[A-Z][a-z]+){0,2}\b"
    )
    TIME_REFERENCE_RE = re.compile(
        r"\b(same time|same day|today|tomorrow|yesterday)\b", re.IGNORECASE
    )
    FILTER_REFERENCE_RE = re.compile(
        r"\b(same filters?|same layers?|same overlay|show traffic|show weather|show air quality)\b",
        re.IGNORECASE,
    )

    # -------------------------------------------------------------------------
    def _is_referential(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.REFERENTIAL_PATTERNS)

    # -------------------------------------------------------------------------
    def _has_new_location_cue(self, text: str) -> bool:
        return bool(
            self.COORDINATE_RE.search(text)
            or self.ADDRESS_RE.search(text)
            or self.CITY_OR_COUNTRY_RE.search(text)
        )

    # -------------------------------------------------------------------------
    def _is_new_task_signal(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in self.NEW_TASK_PATTERNS)

    # -------------------------------------------------------------------------
    def _latest_task_start_index(
        self, history: list[dict[str, Any]], *, current_user_index: int
    ) -> int:
        start_index = 0
        for index, message in enumerate(history[:current_user_index]):
            if str(message.get("role") or "") != "user":
                continue
            content = str(message.get("content") or "")
            if self._is_new_task_signal(content):
                start_index = index
                continue
            if self._has_new_location_cue(content) and not self._is_referential(
                content
            ):
                start_index = index
        return start_index

    # -------------------------------------------------------------------------
    def decide_scope(
        self,
        *,
        history: list[dict[str, Any]],
        user_message: str,
        latest_state: ExtractedIntent,
    ) -> TaskScopeDecision:
        current_user_index = max(0, len(history) - 1)
        referential = self._is_referential(user_message)
        explicit_new_task = self._is_new_task_signal(user_message)
        has_new_location = self._has_new_location_cue(user_message)
        has_persisted_location = bool(
            latest_state.location.address
            or latest_state.location.city
            or latest_state.location.country
            or (
                latest_state.coordinates.latitude is not None
                and latest_state.coordinates.longitude is not None
            )
        )

        starts_new_task = bool(
            explicit_new_task or (has_new_location and not referential)
        )
        if not has_persisted_location and not has_new_location:
            starts_new_task = False

        if starts_new_task:
            return TaskScopeDecision(
                starts_new_task=True,
                carry_forward_location=False,
                carry_forward_time=False,
                carry_forward_filters=False,
                history_start_index=current_user_index,
                reason="Current message contains a new independent location or explicit task reset.",
            )

        history_start_index = self._latest_task_start_index(
            history, current_user_index=current_user_index
        )
        return TaskScopeDecision(
            starts_new_task=False,
            carry_forward_location=has_persisted_location
            and (referential or not has_new_location),
            carry_forward_time=bool(
                referential or self.TIME_REFERENCE_RE.search(user_message)
            ),
            carry_forward_filters=bool(
                referential or self.FILTER_REFERENCE_RE.search(user_message)
            ),
            history_start_index=max(0, history_start_index),
            reason="Message is referential or does not establish a new independent location.",
        )
