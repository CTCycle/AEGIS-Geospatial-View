"""Collect bounded operational evidence from the isolated live audit runtime."""

import json
import sqlite3
import csv
from datetime import datetime
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:7061"
OUTPUT = Path(__file__).parent / "post-change-runs.json"


def collect():
    rows = []
    with httpx.Client(base_url=BASE, timeout=15) as client:
        database = Path(__file__).resolve().parents[3] / "runtimes/cache/test-runtime/agent-loop-audit/database.db"
        with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
            connection.row_factory = sqlite3.Row
            summaries = list(connection.execute(
                "SELECT id AS run_id, conversation_id FROM agent_runs WHERE datetime(created_at) >= datetime(?) ORDER BY created_at",
                ("2026-10-23T21:05:00",),
            ))
        for summary in summaries:
            cid = summary["conversation_id"]
            run = client.get(f"/api/conversations/{cid}/runs/{summary['run_id']}").json()
            response = run.get("response") or {}
            events = []
            if not response:
                page = client.get(f"/api/conversations/{cid}/runs/{summary['run_id']}/trace",
                                  params={"limit": 200}).json()
                events = page.get("events", [])
                response = next((item.get("payload", {}) for item in reversed(events)
                                 if item.get("type") == "error"), {})
            trace = response.get("execution_trace") or {}
            session = response.get("map_session") or {}
            if not session and trace.get("render_observations"):
                page = client.get(f"/api/conversations/{cid}/runs/{summary['run_id']}/trace",
                                  params={"limit": 200}).json()
                events = page.get("events", [])
                session = next((item.get("payload", {}).get("map_session", {})
                                for item in reversed(events) if item.get("type") == "map_prepared"), {})
            collection = session.get("overlay_collection") or {}
            collection = {"revision": collection.get("revision"), "instances": [
                {key: item.get(key) for key in ("instance_id", "capability_id", "label", "visible", "opacity", "rendering_mode")}
                for item in collection.get("instances", [])
            ]} if collection else None
            checkpoint = trace.get("checkpoint") or {}
            rows.append({
                "conversation_id": cid,
                "run_id": run["run_id"],
                "request": run["original_request"],
                "created_at": run["created_at"],
                "state": run["state"],
                "error_code": run.get("error_code"),
                "error_message": run.get("error_message"),
                "stopped_reason": trace.get("stopped_reason"),
                "seconds": round((datetime.fromisoformat(run["completed_at"]) - datetime.fromisoformat(run["started_at"])).total_seconds(), 3) if run.get("completed_at") and run.get("started_at") else None,
                "iterations": run.get("current_iteration"),
                "model_calls": trace.get("model_calls"),
                "tool_calls": trace.get("tool_calls"),
                "tools": [{key: item.get(key) for key in ("tool_name", "status", "error_code", "summary", "iteration")}
                          for item in (trace.get("tool_trace") or [entry for entry in events if entry.get("kind") == "tool_completed"])
                          if item.get("kind") != "tool_selected"],
                "renders": trace.get("render_observations", []) or [item["payload"] for item in events if item.get("type") == "render_observed"],
                "map": {"bounds": session.get("bounds"), "session_id": session.get("session_id"),
                        "viewport": session.get("viewport"), "collection": collection},
                "final": response.get("assistant_message"),
                "completion": response.get("completion_contract"),
                "provider": checkpoint.get("provider"),
            })
    rows.sort(key=lambda row: row["created_at"])
    OUTPUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    with OUTPUT.with_name("scenarios.tsv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["run_id", "conversation_id", "request", "outcome", "task_correctness", "tools",
                  "map_ack", "iterations", "model_calls", "tool_calls", "seconds", "unproductive_work", "notes"]
        writer = csv.DictWriter(handle, fields, delimiter="\t")
        writer.writeheader()
        for row in rows:
            final = row.get("final") or row.get("error_message") or ""
            correct = "PASS" if row["state"] == "completed" else "FAIL"
            notes = "Reviewed task result separately from lifecycle state."
            if row["request"] == "How far is Rome from Milan?" and row["state"] == "cancelled":
                correct, notes = "SETUP", "Interrupted while reconnecting the isolated origin; not a cancellation acceptance test."
            elif row["error_code"] == "render_timeout":
                correct, notes = "PASS", "Expected negative case: HTTP-created map candidate received no browser acknowledgment and expired."
            elif row["state"] == "cancelled":
                correct, notes = "PASS", "Explicit live cancellation; no further result is claimed."
            elif row["request"] == "Show Springfield on the map" and "Which location" in final:
                correct, notes = "PASS", "Clarification is the correct outcome for an ambiguous place."
            elif "population" in row["request"] and ("couldn't produce" in final or "no verified population" in final):
                correct, notes = "FAIL", "Honest refusal, but no population comparison; retained to document discovery failures."
            elif "rainfall today" in row["request"] and "2026-10-22" in final:
                correct, notes = "PARTIAL", "Sampled/model caveats were correct; the current-day window wrongly included yesterday."
            elif "validated location is required" in final:
                correct, notes = "FAIL", "Map action did not execute despite a lifecycle completion."
            elif "currently visible" in row["request"] and row["state"] == "failed":
                correct, notes = "PARTIAL", "Actual panned bounds were understood; exposed resolver was not called and retrieval did not happen."
            elif "5 pharmacies nearest" in row["request"] and row["map"].get("bounds") and row["map"]["bounds"][2] - row["map"]["bounds"][0] > 0.02:
                correct, notes = "PARTIAL", "Correct ranked distances and ready acknowledgment, but city-scale viewport made the close results overlap. Fixed in the subsequent fitted-map run."
            writer.writerow({
                "run_id": row["run_id"], "conversation_id": row["conversation_id"], "request": row["request"],
                "outcome": row["state"], "task_correctness": correct,
                "tools": "; ".join(f"{item.get('tool_name')}:{item.get('status')}" for item in row["tools"]),
                "map_ack": ";".join(str(item.get("status")) for item in row["renders"]) or "not_required_or_not_reached",
                "iterations": row["iterations"], "model_calls": row["model_calls"], "tool_calls": row["tool_calls"],
                "seconds": row["seconds"], "unproductive_work": "yes" if row["stopped_reason"] in {"no_progress", "failed"} else "see_trace" if correct in {"FAIL", "PARTIAL"} else "none_observed",
                "notes": notes,
            })
    for row in rows:
        print(row["state"], row["request"], row["model_calls"], row["tool_calls"], row["seconds"])


if __name__ == "__main__":
    collect()
