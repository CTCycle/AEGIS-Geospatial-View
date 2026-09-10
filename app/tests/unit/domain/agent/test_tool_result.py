from __future__ import annotations

import pytest
from pydantic import ValidationError

from server.domain.agent.tool_result import (
    ToolExecutionError,
    ToolExecutionMetadata,
    ToolResult,
    ValidationIssue,
)


def test_tool_result_has_one_strict_model_visible_shape() -> None:
    result = ToolResult(
        call_id="call-1",
        tool_name="resolve_geospatial_location",
        status="success",
        summary="Resolved Zurich.",
        metadata=ToolExecutionMetadata(duration_ms=12),
    )

    assert result.status == "success"
    assert result.metadata.duration_ms == 12

    with pytest.raises(ValidationError):
        ToolResult(
            call_id="call-1",
            tool_name="resolve_geospatial_location",
            status="not-a-status",
            summary="bad",
            metadata=ToolExecutionMetadata(duration_ms=0),
        )

    with pytest.raises(ValidationError):
        ToolResult(
            call_id="call-1",
            tool_name="resolve_geospatial_location",
            status="failed",
            summary="bad",
            metadata=ToolExecutionMetadata(duration_ms=0),
            unexpected=True,
        )


def test_tool_execution_error_restricts_recovery_and_issue_shape() -> None:
    error = ToolExecutionError(
        error_type="schema_validation",
        code="missing_query",
        message="The query is required.",
        retryable=False,
        recovery="correct_arguments",
        validation_errors=[
            ValidationIssue(path="query", code="missing", message="Required.")
        ],
    )

    assert error.validation_errors[0].path == "query"
    with pytest.raises(ValidationError):
        ToolExecutionError(
            error_type="schema_validation",
            code="bad",
            message="bad",
            retryable=False,
            recovery="retry_forever",
        )
