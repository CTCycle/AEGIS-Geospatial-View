"""Backend memory benchmark for the three payload-heavy read paths.

Seeds a disposable SQLite database with rows sized like the production
database (see report.md) and measures, per scenario:

- ``peak_alloc_mib``: tracemalloc peak of Python allocations for one pass.
- ``rss_delta_mib``: growth of process working set across the repetitions,
  and ``rss_peak_mib``: peak working set of the whole process (OS-level).

Scenarios:
- ``snapshot_messages``: message list the conversation snapshot builds.
- ``evidence_summaries``: ``list_summaries(limit=100)`` run on every agent turn.
- ``event_stream``: replaying a finished run's user events to a subscriber
  (consuming ``RunEventPublisher.events`` until the terminal event).
- ``terminal_lookup``: the final-response lookup ``read_completed_response`` does
  (newest completed event of a finished run).

The same script runs on the baseline and the optimized commit; it adapts to the
renamed repository method.

Usage (repository root):
    app/server/.venv/Scripts/python.exe scripts/benchmarks/memory_benchmark.py \
        --output assets/QA/<folder>/<label>.json
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import gc
import json
import random
import subprocess
import sys
import tempfile
import tracemalloc
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "app"))

from server.configurations import DatabaseSettings  # noqa: E402
from server.contracts.events import RunEventCreate, RunEventType, RunEventVisibility  # noqa: E402
from server.repositories.agent_evidence import AgentEvidenceRepository  # noqa: E402
from server.repositories.agent_run_events import AgentRunEventRepository  # noqa: E402
from server.repositories.agent_runs import AgentRunRepository  # noqa: E402
from server.repositories.chat_history import ChatHistoryRepository  # noqa: E402
from server.repositories.conversations import ConversationRepository  # noqa: E402
from server.repositories.database.sqlite import SQLiteRepository  # noqa: E402
from server.repositories.schemas import Base  # noqa: E402
from server.repositories.schemas.models import ChatMessageRecord  # noqa: E402
from server.services.agent_runs.events import RunEventPublisher  # noqa: E402
from server.services.chat.history_service import ChatHistoryService  # noqa: E402

MESSAGE_COUNT = 200
EVIDENCE_ROWS = 100
EVIDENCE_PAYLOAD_MIB = 0.5
BIG_EVENT_MIB = 3.5
SMALL_EVENTS = 30


###############################################################################
class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


# -----------------------------------------------------------------------------
def _working_set_mib() -> tuple[float, float]:
    """Return (current, peak) working set of this process in MiB."""

    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessMemoryCounters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize / 2**20, counters.PeakWorkingSetSize / 2**20


###############################################################################
def _random_text(rng: random.Random, size: int) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789 "
    return "".join(rng.choices(alphabet, k=size))


# -----------------------------------------------------------------------------
def _feature_payload(rng: random.Random, target_bytes: int) -> dict[str, Any]:
    count = max(1, target_bytes // 90)
    return {
        "features": [
            {
                "id": index,
                "lon": round(rng.uniform(-180, 180), 5),
                "lat": round(rng.uniform(-90, 90), 5),
                "value": round(rng.uniform(0, 100), 3),
            }
            for index in range(count)
        ]
    }


###############################################################################
def _seed_messages(database: SQLiteRepository, conversation_id: str, rng: random.Random) -> None:
    """Average ~114 KB per message, matching the production payload columns."""

    with database.session() as session:
        for index in range(MESSAGE_COUNT):
            assistant = index % 2 == 1
            session.add(
                ChatMessageRecord(
                    conversation_id=conversation_id,
                    turn_index=index + 1,
                    request_id=f"bench-{index // 2}",
                    role="assistant" if assistant else "user",
                    content=f"Message {index}: show the weather around the Colosseum.",
                    structured_payload=_feature_payload(rng, 26_000) if assistant else None,
                    tool_payload=_feature_payload(rng, 28_000) if assistant else None,
                    map_session=_feature_payload(rng, 170_000) if assistant else None,
                )
            )
        session.commit()


# -----------------------------------------------------------------------------
def _seed_run_events(
    conversations: ConversationRepository,
    runs: AgentRunRepository,
    events: AgentRunEventRepository,
    rng: random.Random,
) -> str:
    conversation = conversations.create_conversation("event benchmark")
    snapshot = runs.create_run(conversation.id, "Show Rome", "Show Rome")

    def append(event_type: RunEventType, payload: dict[str, Any]) -> None:
        events.append_event(
            RunEventCreate(
                conversation_id=conversation.id,
                run_id=snapshot.run_id,
                run_version=snapshot.active_run_version,
                type=event_type,
                visibility=RunEventVisibility.USER,
                payload=payload,
            )
        )

    for index in range(SMALL_EVENTS):
        append(RunEventType.TRACE, {"kind": "progress", "step": index, "note": "x" * 300})
    big = int(BIG_EVENT_MIB * 2**20)
    append(RunEventType.MAP_PREPARED, _feature_payload(rng, big))
    append(RunEventType.COMPLETED, {"assistant_message": "done", **_feature_payload(rng, big)})
    return snapshot.run_id


# -----------------------------------------------------------------------------
def _seed_evidence(
    evidence: AgentEvidenceRepository, conversation_id: str, rng: random.Random
) -> None:
    for _ in range(EVIDENCE_ROWS):
        payload = _feature_payload(rng, int(EVIDENCE_PAYLOAD_MIB * 2**20))
        evidence.create(
            conversation_id=conversation_id,
            run_id=None,
            kind="vector",
            media_type="application/json",
            status="available",
            payload=payload,
            summary={"feature_count": len(payload["features"])},
            provenance={"provider_id": "benchmark"},
        )


###############################################################################
def _measure(operation: Callable[[], object], repetitions: int) -> dict[str, Any]:
    operation()  # warm connection pool and statement cache
    gc.collect()
    before, _ = _working_set_mib()
    for _ in range(repetitions):
        operation()
    after, peak = _working_set_mib()
    gc.collect()
    tracemalloc.start()
    operation()
    traced_peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return {
        "repetitions": repetitions,
        "peak_alloc_mib": round(traced_peak / 2**20, 2),
        "rss_start_mib": round(before, 1),
        "rss_peak_mib": round(peak, 1),
        "rss_delta_mib": round(after - before, 1),
    }


# -----------------------------------------------------------------------------
async def _stream_until_terminal(publisher: RunEventPublisher, run_id: str) -> int:
    seen = 0
    async for event in publisher.events(run_id):
        seen += 1
        if event.type in {RunEventType.COMPLETED, RunEventType.CANCELLED, RunEventType.ERROR}:
            break
    return seen


###############################################################################
def _open(path: Path) -> tuple[SQLiteRepository, dict[str, Any]]:
    database = SQLiteRepository(DatabaseSettings(str(path)))
    return database, {
        "conversations": ConversationRepository(database),
        "events": AgentRunEventRepository(database),
        "history": ChatHistoryService(ChatHistoryRepository(database)),
        "evidence": AgentEvidenceRepository(database),
    }


# -----------------------------------------------------------------------------
def _seed(path: Path) -> dict[str, str]:
    rng = random.Random(20261109)
    database, repos = _open(path)
    Base.metadata.create_all(database.engine)
    runs = AgentRunRepository(database, event_repository=repos["events"])
    message_conversation = repos["conversations"].create_conversation("messages").id
    _seed_messages(database, message_conversation, rng)
    evidence_conversation = repos["conversations"].create_conversation("evidence").id
    _seed_evidence(repos["evidence"], evidence_conversation, rng)
    run_id = _seed_run_events(repos["conversations"], runs, repos["events"], rng)
    database.engine.dispose()
    return {
        "message_conversation": message_conversation,
        "evidence_conversation": evidence_conversation,
        "run_id": run_id,
    }


# -----------------------------------------------------------------------------
def _run_scenario(name: str, path: Path, meta: dict[str, str], repetitions: int) -> dict[str, Any]:
    database, repos = _open(path)
    history = repos["history"]
    if name == "snapshot_messages":
        list_messages = getattr(history, "list_message_headers", None) or history.list_messages
        operation: Callable[[], object] = lambda: list_messages(
            conversation_id=meta["message_conversation"]
        )
    elif name == "evidence_summaries":
        operation = lambda: repos["evidence"].list_summaries(meta["evidence_conversation"], limit=100)
    elif name == "terminal_lookup":
        publisher = RunEventPublisher(repos["events"])
        completed = {RunEventType.COMPLETED, RunEventType.CLARIFICATION_NEEDED}

        def operation() -> object:
            if hasattr(publisher, "latest_event"):
                return publisher.latest_event(meta["run_id"], types=frozenset(completed))
            return next(
                event for event in reversed(publisher.replay(meta["run_id"]))
                if event.type in completed
            )
    else:
        publisher = RunEventPublisher(repos["events"])
        operation = lambda: asyncio.run(_stream_until_terminal(publisher, meta["run_id"]))
    result = _measure(operation, repetitions)
    database.engine.dispose()
    return result


# -----------------------------------------------------------------------------
SCENARIOS = ("snapshot_messages", "evidence_summaries", "event_stream", "terminal_lookup")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=10)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scenario", choices=SCENARIOS, help="internal: child process mode")
    parser.add_argument("--db", type=Path, help="internal: child process mode")
    args = parser.parse_args()

    if args.scenario:
        meta = json.loads(args.db.with_suffix(".json").read_text(encoding="utf-8"))
        print(json.dumps(_run_scenario(args.scenario, args.db, meta, args.repetitions)))
        return

    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip()
    results: dict[str, Any] = {"commit": commit, "scenarios": {}}
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "bench.db"
        path.with_suffix(".json").write_text(json.dumps(_seed(path)), encoding="utf-8")
        results["db_size_mib"] = round(path.stat().st_size / 2**20, 1)
        # One fresh process per scenario so peak working set is not polluted.
        for name in SCENARIOS:
            completed = subprocess.run(
                [sys.executable, __file__, "--scenario", name, "--db", str(path),
                 "--repetitions", str(args.repetitions)],
                capture_output=True, text=True, check=True,
            )
            results["scenarios"][name] = json.loads(completed.stdout.strip().splitlines()[-1])

    rendered = json.dumps(results, indent=2)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
