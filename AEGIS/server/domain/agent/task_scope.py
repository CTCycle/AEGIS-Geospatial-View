from __future__ import annotations

from pydantic import BaseModel, Field


class TaskScopeDecision(BaseModel):
    starts_new_task: bool = False
    carry_forward_location: bool = True
    carry_forward_time: bool = True
    carry_forward_filters: bool = True
    history_start_index: int = Field(default=0, ge=0)
    reason: str = ""
