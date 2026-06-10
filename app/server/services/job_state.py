from __future__ import annotations

import threading
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from server.domain.jobs import BackgroundJobState


@dataclass
class JobState(BackgroundJobState):
    lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def update(self, **kwargs: Any) -> None:
        with self.lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "job_id": self.job_id,
                "job_type": self.job_type,
                "status": self.status,
                "progress": self.progress,
                "result": self.result,
                "error": self.error,
                "created_at": self.created_at,
                "completed_at": self.completed_at,
            }
