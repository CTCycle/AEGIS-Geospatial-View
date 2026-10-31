"""Reproducible database baseline for the agent loop's per-check and per-turn work.

Measures, against a disposable file-backed SQLite database, the two hot paths
targeted by the agent-loop optimization plan:

- ``run_control``: one run-state check, as issued by the run coordinator for
  every trace, checkpoint and cancellation probe, against a run with 256 events.
- ``turn_history``: the conversation-history work performed once per agent
  turn, for conversations of 10, 500, 5,000 and 10,000 messages.

Each scenario reports SQL statement count, median/p95 wall time and peak
Python allocation. Results are printed as JSON; pass ``--output`` to save them.

Usage (from the repository root):
    app/server/.venv/Scripts/python.exe scripts/benchmarks/agent_loop_db.py \
        --output assets/QA/<folder>/agent-loop-db-<label>.json
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))

from sqlalchemy import event  # noqa: E402

from server.configurations import DatabaseSettings  # noqa: E402
from server.contracts.events import RunEventCreate, RunEventType, RunEventVisibility  # noqa: E402
from server.repositories.agent_run_events import AgentRunEventRepository  # noqa: E402
from server.repositories.agent_runs import AgentRunRepository  # noqa: E402
from server.repositories.chat_history import ChatHistoryRepository  # noqa: E402
from server.repositories.conversations import ConversationRepository  # noqa: E402
from server.repositories.database.sqlite import SQLiteRepository  # noqa: E402
from server.repositories.schemas import Base  # noqa: E402
from server.repositories.schemas.models import ChatMessageRecord  # noqa: E402
from server.services.chat.history_service import ChatHistoryService  # noqa: E402

HISTORY_SIZES = (10, 500, 5_000, 10_000)
RUN_EVENT_COUNT = 256
HISTORY_LIMIT = 10_000


###############################################################################
class _StatementCounter:

    # -------------------------------------------------------------------------
    def __init__(self, database: SQLiteRepository) -> None:
        self.count = 0
        event.listen(database.engine, "before_cursor_execute", self._on_execute)

    # -------------------------------------------------------------------------
    def _on_execute(self, *_args: Any) -> None:
        self.count += 1


###############################################################################
def _seed_history(database: SQLiteRepository, conversation_id: str, size: int) -> None:
    """Insert realistic rows, including the heavy JSON columns real turns carry."""

    map_session = {
        "session_id": "bench",
        "overlay_collection": {
            "revision": 1,
            "features": [
                {"id": index, "coordinates": [12.49 + index / 1e4, 41.89]}
                for index in range(200)
            ],
        },
    }
    tool_payload = {
        "tool_calls": [
            {"name": "search_location", "arguments": {"query": "Rome"}, "status": "success"}
            for _ in range(4)
        ]
    }
    with database.session() as session:
        session.add_all(
            ChatMessageRecord(
                conversation_id=conversation_id,
                turn_index=index + 1,
                request_id=f"bench-{index // 2}",
                role="user" if index % 2 == 0 else "assistant",
                content=f"Message {index}: show the weather around the Colosseum. " * 4,
                structured_payload={"request_id": f"bench-{index // 2}", "native": True},
                tool_payload=tool_payload if index % 2 else None,
                map_session=map_session if index % 2 else None,
            )
            for index in range(size)
        )
        session.commit()


###############################################################################
def _seed_run(
    conversations: ConversationRepository,
    runs: AgentRunRepository,
    events: AgentRunEventRepository,
) -> str:
    conversation = conversations.create_conversation("run-control benchmark")
    snapshot = runs.create_run(conversation.id, "Show Rome", "Show Rome")
    for sequence in range(RUN_EVENT_COUNT):
        events.append_event(
            RunEventCreate(
                conversation_id=conversation.id,
                run_id=snapshot.run_id,
                run_version=snapshot.active_run_version,
                type=RunEventType.TRACE,
                visibility=RunEventVisibility.INTERNAL,
                payload={"kind": "tool_result", "sequence": sequence, "summary": "x" * 400},
            )
        )
    return snapshot.run_id


###############################################################################
def run_control_check(runs: AgentRunRepository, run_id: str, version: int) -> str | None:
    """Mirror ``AgentRunOrchestrator``'s per-trace run-state check."""

    control = runs.get_run_control(run_id)
    if control is None or control.cancel_requested_at is not None:
        return "cancelled"
    if control.active_run_version != version:
        return "superseded"
    return None


###############################################################################
def turn_history(history: ChatHistoryService, conversation_id: str) -> int:
    """Mirror ``NativeAgentOrchestrator``'s per-turn history reads."""

    recent_count = history.count_messages(conversation_id)
    messages = history.list_context_messages(conversation_id, limit=HISTORY_LIMIT)
    return recent_count + len(messages)


###############################################################################
def _measure(
    counter: _StatementCounter,
    operation: Callable[[], object],
    repetitions: int,
) -> dict[str, Any]:
    operation()  # warm the connection pool and statement cache
    durations: list[float] = []
    statements: list[int] = []
    for _ in range(repetitions):
        counter.count = 0
        started = time.perf_counter()
        operation()
        durations.append((time.perf_counter() - started) * 1_000)
        statements.append(counter.count)
    # Allocation tracing is slow, so peak memory comes from one separate pass.
    tracemalloc.start()
    operation()
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    ordered = sorted(durations)
    return {
        "repetitions": repetitions,
        "sql_statements": max(statements),
        "median_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[max(0, round(0.95 * len(ordered)) - 1)], 3),
        "peak_alloc_kib": round(peak / 1024, 1),
    }


###############################################################################
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    def git(*command: str) -> str:
        return subprocess.run(
            ["git", *command], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()

    results: dict[str, Any] = {
        "commit": git("rev-parse", "HEAD"),
        "dirty_worktree": bool(git("status", "--porcelain", "--untracked-files=no")),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scenarios": {},
    }
    with tempfile.TemporaryDirectory() as directory:
        database = SQLiteRepository(DatabaseSettings(str(Path(directory) / "bench.db")))
        Base.metadata.create_all(database.engine)
        conversations = ConversationRepository(database)
        events = AgentRunEventRepository(database)
        runs = AgentRunRepository(database, event_repository=events)
        history = ChatHistoryService(ChatHistoryRepository(database))
        counter = _StatementCounter(database)

        run_id = _seed_run(conversations, runs, events)
        results["scenarios"]["run_control"] = _measure(
            counter, lambda: run_control_check(runs, run_id, 1), args.repetitions * 10
        )
        for size in HISTORY_SIZES:
            conversation_id = conversations.create_conversation(f"history {size}").id
            _seed_history(database, conversation_id, size)
            results["scenarios"][f"turn_history_{size}"] = _measure(
                counter, lambda: turn_history(history, conversation_id), args.repetitions
            )
        database.engine.dispose()

    rendered = json.dumps(results, indent=2)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
