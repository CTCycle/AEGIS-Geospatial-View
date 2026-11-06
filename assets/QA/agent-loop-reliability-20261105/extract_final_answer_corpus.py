"""Export the final-answer replay corpus from the recorded live suite runs.

Read-only against the runtime database. Run from the repository root:

    PYTHONPATH=app/server app/server/.venv/Scripts/python \
        assets/QA/agent-loop-reliability-20261105/extract_final_answer_corpus.py

A case pairs one run's last checkpoint (the inputs of the gate) with an answer
and a human verdict. Runs up to r5 stored only the violations of a replaced
answer, not its text (later runs keep it as ``rejected_answer`` in the
finalization trace), so each case states where its candidate came from:

- ``recorded``: this run's own model text, rejected or delivered (server disclosure removed).
- ``other_sample``: the model text another recorded run gave to the same request.
- ``reconstructed``: minimal text around the fragment the recorded violation quotes.
- ``synthetic_guard``: invented false claim that guards a loosened check.

Verdicts come from the per-scenario tables of ``after*.md``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "app"))

from server.domain.agent.capability_route import AgentRunState  # noqa: E402
from server.domain.agent.reliability import AgentExecutionBudget  # noqa: E402
from server.services.agent import agent_loop  # noqa: E402

QA = Path(__file__).resolve().parent
OUTPUT = ROOT / "app/tests/fixtures/agent/final_answer_replay.json"
SUITES = {"r2": "after-r2", "r3": "after-r3", "r4": "after-r4", "r5": "after-r5"}

# Scenario verdicts of the per-scenario tables (scenarios absent here failed).
PASSED = {
    "r2": "S01 S04 S05 S07 S08 S09 S10 S11 S12 S13 S14 S15",
    "r3": "S01 S02 S04 S05 S06 S07 S09 S10 S11 S13 S14 S15",
    "r4": "S01 S02 S03 S04 S05 S06 S07 S08 S09 S10 S11 S14 S15",
    "r5": "S01 S02 S03 S04 S05 S06 S07 S08 S09 S10 S11 S13",
}
SCENARIOS = {
    "What is the current temperature": "S01", "Compare today's temperatures": "S02",
    "Show the Brandenburg Gate": "S03", "Show me Rome": "S04",
    "Show me Springfield": "S05", "The one in Massachusetts": "S05",
    "How windy is it": "S06", "Show earthquakes of magnitude 15": "S07",
    "Show earthquakes of magnitude 4.5": "S08", "Which one was strongest": "S08",
    "What are today's temperatures": "S09", "Now compare precipitation": "S09",
    "Show earthquakes of magnitude 5": "S10", "Same thing but only": "S10",
    "Show me Lisbon": "S11", "Show me Vienna": "S12", "What is the temperature in Vienna": "S12",
    "And in Prague": "S12", "Which of the two is warmer": "S12", "Now show Prague": "S12",
    "Show me the current wildfire": "S13", "Write a haiku": "S14", "Show 46.0037": "S15",
    "Show the current weather radar": "S16", "Remove that layer": "S16",
}
# A failing scenario's other turns the report calls correct.
EXTRA_ACCEPTED = {"404f0b": "after-r5 S12: T2 correct", "c10e20": "after-r5 S12: T3 correct", "b7c69b": "after-r5 S12: T4 correct"}

# Serialized state the gate, the summary and the fallbacks never read.
_UNREAD = (
    "recent_messages", "context_usage_trace", "model_trace", "tool_trace", "provider_continuation",
    "execution_policy", "transition_trace", "exposure_trace", "iteration_trace", "budget_snapshot",
    "context_allocation", "map_memory", "successful_fingerprints", "failed_render_fingerprints",
    "policy_constraints", "active_directives", "summary", "included_message_ids", "omitted_message_ids",
)
_SECRET = re.compile(r"api[_-]?key|apikey|secret|password|bearer\s|authorization|access_token|\bsk-[a-z0-9]{8}", re.I)
_DISCLOSURE_TAIL = re.compile(r"\n\n(?:Not delivered|Not completed|Map check|The map layer shows only|Note:|The map could not).*", re.S)
_SERVER_TEXT = re.compile(r"^(?:Results gathered|No supported capability|The model's answer|The map now shows|The map is ready\.?$|Map state update|The map candidate)")


###############################################################################
class Store:
    def __init__(self) -> None:
        self.db = sqlite3.connect(f"file:{ROOT / 'data/database.db'}?mode=ro", uri=True)

    # -------------------------------------------------------------------------
    def run(self, prefix: str) -> dict[str, Any]:
        run_id, request = self.db.execute(
            "select id, original_request from agent_runs where id like ?", (f"run_{prefix}%",)
        ).fetchone()
        run: dict[str, Any] = {
            "id": run_id, "request": request, "answer": "", "state": None,
            "outcomes": [], "reasons": [], "violations": [], "rejected_answer": "",
        }
        rows = self.db.execute(
            "select type, payload_json from agent_run_events where run_id = ? order by sequence", (run_id,)
        )
        for kind, raw in rows:
            payload = json.loads(raw)
            if kind == "checkpoint":
                run["state"] = payload["payload"]["run_state"]
            elif kind == "completed":
                run["answer"] = payload.get("assistant_message") or ""
            elif kind == "trace" and str(payload.get("kind", "")).startswith("finalization_"):
                detail = payload["payload"]
                if detail.get("outcome"):
                    run["outcomes"].append(detail["outcome"])
                else:
                    run["reasons"].append(detail.get("reason"))
                run["violations"].extend(detail.get("final_answer_violations", []))
                run["rejected_answer"] = detail.get("rejected_answer") or run["rejected_answer"]
        return run

    # -------------------------------------------------------------------------
    def model_text(self, prefix: str) -> str:
        run = self.run(prefix)
        return run["rejected_answer"] or _DISCLOSURE_TAIL.sub("", run["answer"]).strip()


###############################################################################
def scenario_of(request: str) -> str:
    return next(value for key, value in SCENARIOS.items() if request.startswith(key))


###############################################################################
def path_of(run: dict[str, Any]) -> str:
    """The finalization path of a run; a stop without a synthesis call is 'text_stop'."""

    if "verified_render" in run["reasons"]:
        return "verified_render"
    return "completed" if "goal_satisfied" in run["reasons"] else "text_stop"


###############################################################################
def judged_runs(report: str) -> list[str]:
    lines = (QA / f"run-metrics-{report}.txt").read_text(encoding="utf-8").splitlines()
    runs = (re.match(r"([0-9a-f]{6}) ([0-9a-f]{6}) ", line) for line in lines)
    return [match[2] for match in runs if match]


###############################################################################
def trim(state: dict[str, Any]) -> dict[str, Any]:
    """Keep what the gate reads; cut big non-marker layer payloads and URL queries."""

    trimmed = {key: value for key, value in state.items() if key not in _UNREAD and value not in (None, [], {})}
    trimmed["task_state"] = {
        key: value for key, value in state.get("task_state", {}).items()
        if key in {"schema_version", "conversation_id", "root_task_id", "active_task_id", "status", "tasks", "current_iteration", "max_iterations", "completion_requirements"}
    }
    trimmed["relevant_tool_outcomes"] = [
        {key: value for key, value in item.items() if key in {"evidence_id", "observation_type", "summary", "status"}}
        for item in state.get("relevant_tool_outcomes", [])
    ]
    for key in ("active_map_session", "prepared_map_session"):
        for instance in ((trimmed.get(key) or {}).get("overlay_collection") or {}).get("instances", []):
            data = (instance.get("descriptor") or {}).get("data")
            if isinstance(data, dict) and isinstance(data.get("features"), list) and instance.get("instance_id") != agent_loop.PLACE_MARKERS_INSTANCE_ID:
                data["features"] = data["features"][:2]
    text = json.dumps(trimmed, ensure_ascii=False)
    text = re.sub(r"(https?://[^\"?\s]+)\?[^\"\s]*", r"\1", text)
    return json.loads(text)


###############################################################################
def gate_view(loop: agent_loop.AgentLoop, payload: dict[str, Any]) -> dict[str, Any]:
    """Everything replay reads from one state, to prove trimming changes nothing."""

    state = AgentRunState.from_checkpoint(json.loads(json.dumps(payload)))
    captured: dict[str, Any] = {}

    def capture(text: str, **kwargs: Any) -> list[str]:
        captured.update(kwargs)
        return []

    original = agent_loop.check_final_answer
    agent_loop.check_final_answer = capture
    try:
        request = agent_loop.AgentLoopRequest(
            provider="fake", model="fake", state=state,
            budget=AgentExecutionBudget(total_seconds=10, hard_max_seconds=10),
        )
        asyncio.run(loop._verified_answer_text(request, "x", reason="replay"))  # pyright: ignore[reportPrivateUsage]
    finally:
        agent_loop.check_final_answer = original
    return {
        "gate": captured,
        "summary": loop.completion_summary(state).model_dump(mode="json"),
        "disclosure": loop.completion_summary(state).disclosure(),
        "findings": loop._evidence_findings(state),  # pyright: ignore[reportPrivateUsage]
        "evidence": loop._evidence_summary(state),  # pyright: ignore[reportPrivateUsage]
        "map_fallback": loop._verified_map_fallback(state),  # pyright: ignore[reportPrivateUsage]
        "map_state": loop._verified_map_state_summary(state),  # pyright: ignore[reportPrivateUsage]
    }


###############################################################################
def build() -> dict[str, Any]:
    store = Store()
    loop = agent_loop.AgentLoop.__new__(agent_loop.AgentLoop)
    cases: list[dict[str, Any]] = []
    states: dict[str, dict[str, Any]] = {}

    def add(prefix: str, label: str, candidate: str, source: str, verdict: str, **expect: Any) -> None:
        run = store.run(prefix)
        states.setdefault(prefix, run["state"])
        path = expect.pop("path", path_of(run))
        cases.append({
            "id": f"{scenario_of(run['request'])}-{prefix}-{label}-{source}",
            "run": prefix, "request": run["request"], "label": label, "path": path,
            "candidate": candidate, "candidate_source": source, "verdict": verdict,
            "recorded_violations": run["violations"],
            **expect,
        })

    # Delivered model answers of passing scenarios must keep passing.
    for suite, report in SUITES.items():
        for prefix in judged_runs(report):
            run = store.run(prefix)
            scenario = scenario_of(run["request"])
            if (scenario not in PASSED[suite].split() and prefix not in EXTRA_ACCEPTED) or not run["answer"]:
                continue
            if {"answer_replaced", "protocol_text_suppressed", "empty"} & set(run["outcomes"]):
                continue
            text = store.model_text(prefix)
            if _SERVER_TEXT.match(text) or (run["state"].get("route") is None):
                continue
            add(prefix, "accept", text, "recorded", EXTRA_ACCEPTED.get(prefix, f"{report} {scenario}: PASS"))

    # The replaced answers the reports call wrong replacements.
    haiku = store.model_text("1c6184")
    add("95e851", "accept", haiku, "other_sample", "after-r5 S14: the fallback replaced a valid haiku", must_contain=["Leaves drift"])
    s15_good = store.model_text("39b237")
    add("9ab214", "accept", s15_good, "other_sample", "after-r5 S15: Lugano was resolved, the answer named it", must_contain=["Lugano"], must_not_contain=["Not delivered"])
    add("4d78c8", "accept", store.model_text("c86324"), "other_sample", "after-r5 S12-T5: map render-verified on Prague", must_not_contain=["Not delivered"])
    add("0e7d5c", "accept", "Lisbon, Portugal is now shown on the map, centred near latitude 38.7078°.", "reconstructed", "after-r4 S11: PASS; the coordinate is the resolved centre")
    add("01f484", "accept", "Springfield, Massachusetts is now shown on the map, centred near latitude 42.1019°.", "reconstructed", "after-r2 S05: PASS; the coordinate is the resolved centre")
    add("8b4603", "accept", "Vienna was about 9.9 °C earlier, but the temperature for Prague could not be retrieved, so I cannot say which is warmer.", "reconstructed", "after-r5 S12 probe T4: 9.9 °C is the prior turn's verified value")
    add("68e524", "accept", store.model_text("9e32c3"), "other_sample", "after-r5 S13: an offer to show imagery is not a claim that a map exists")

    # Known-bad answers must stay rejected.
    s15_bad = "The map now shows 46.0037, 8.9511 on the OpenStreetMap basemap."  # after.md S15, firm false success
    add("9ab214", "reject", s15_bad, "other_sample", "after S15: place question dropped", must_contain=["Lugano"], must_not_contain=["Not delivered"])
    add("32c167", "reject", s15_bad, "other_sample", "after S15: place question dropped", must_contain=["Lugano"])
    removed = store.model_text("e89090")
    add("e89090", "reject", removed, "recorded", "after-r2 S16-T2: claims a removal although no layer existed", must_not_contain=["been removed"])
    add("bb0c10", "reject", removed, "other_sample", "after-r2 S16-T2: claims a removal although no layer existed", must_not_contain=["been removed"])
    add("c91465", "reject", store.model_text("c91465"), "recorded", "after S10-T1: 'the map shows all 205' with 25 in the layer", must_not_contain=["all 205"])
    add("e4a4ec", "reject", store.model_text("e4a4ec"), "recorded", "after S08-T1: 91 events claimed with 25 in the layer")
    add("3b6812", "reject", "The map shows all 207 events worldwide.", "reconstructed", "after-r5 S10-T1: recorded violation quotes '207 events'")
    add("68e524", "reject", "The map now shows the current wildfire hotspots in Portugal.", "reconstructed", "after-r5 S13: no verified map or data")
    add("3a737e", "reject", store.model_text("c10e20"), "other_sample", "after-r5 S12 probe T3: no Prague data retrieved in this run")
    add("0e7d5c", "reject", "Lisbon, Portugal is now shown on the map, centred near latitude 45.5000°.", "synthetic_guard", "guards the coordinate exemption")
    add("8b4603", "reject", "Vienna was about 12.3 °C, but the temperature for Prague could not be retrieved.", "synthetic_guard", "guards the prior-evidence exemption")

    trimmed: dict[str, dict[str, Any]] = {}
    for prefix, state in states.items():
        trimmed[prefix] = trim(state)
        if gate_view(loop, state) != gate_view(loop, trimmed[prefix]):
            raise SystemExit(f"trimming changed the gate inputs of run {prefix}")
    text = json.dumps(trimmed, ensure_ascii=False)
    if leak := _SECRET.search(text):
        raise SystemExit(f"possible secret in the corpus: {text[max(0, leak.start() - 40) : leak.end() + 40]}")
    return {
        "source": "Recorded runs of assets/QA/agent-loop-reliability-20261105; see extract_final_answer_corpus.py.",
        "cases": cases,
        "states": trimmed,
    }


###############################################################################
if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    corpus = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(corpus, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    labels = [item["label"] for item in corpus["cases"]]
    print(f"{len(labels)} cases ({labels.count('accept')} accept, {labels.count('reject')} reject), "
          f"{len(corpus['states'])} states, {OUTPUT.stat().st_size // 1024} KiB")
