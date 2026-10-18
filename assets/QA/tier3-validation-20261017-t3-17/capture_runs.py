"""Export bounded public run evidence from this disposable validation backend."""

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:5079"


def read(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as response:
        return json.load(response)


def map_summary(value):
    return {
        key: value.get(key)
        for key in ("session_id", "resolved_location", "basemap_id", "basemap", "bounds", "viewport")
    } | {
        "overlays": [
            {key: item.get(key) for key in ("instance_id", "capability_id", "provider", "label")}
            for item in value.get("overlay_collection", {}).get("instances", [])
        ]
    }


output = ROOT / "run-evidence.json"
previous = json.loads(output.read_text(encoding="utf-8")) if output.exists() else []
results = []
for conversation in read("/api/conversations?limit=50")["conversations"]:
    cid = conversation["conversation_id"]
    snapshot = read(f"/api/conversations/{cid}")
    for run in snapshot.get("recent_runs", []):
        rid = run["run_id"]
        trace = read(f"/api/conversations/{cid}/runs/{rid}/trace?limit=200&include_internal=true")
        events = []
        for event in trace["events"]:
            kind, payload = event["type"], event.get("payload", {})
            if kind == "map_prepared":
                presentation = payload.get("presentation", {})
                safe = {
                    "map_session": map_summary(payload.get("map_session", {})),
                    "requirements": presentation.get("completion_requirements"),
                    "required_overlay_ids": presentation.get("required_overlay_ids"),
                }
            elif kind == "render_observed":
                safe = payload
            elif kind == "tool_completed":
                safe = {key: payload.get(key) for key in ("tool_name", "status", "summary", "error")}
            elif kind in {"completed", "error"}:
                safe = {key: payload.get(key) for key in (
                    "assistant_message", "content", "code", "message", "route", "goal",
                    "completion_contract", "presentation_status", "render_acknowledgment",
                ) if key in payload}
                execution = payload.get("execution_trace", {})
                safe["execution"] = {key: execution.get(key) for key in (
                    "stopped_reason", "model_calls", "tool_calls", "render_attempts", "render_verified",
                )}
                if isinstance(payload.get("map_session"), dict):
                    safe["map_session"] = map_summary(payload["map_session"])
            else:
                continue
            events.append({"type": kind, "sequence": event["sequence"], "payload": safe})
        results.append({
            "conversation_id": cid, "run_id": rid,
            "request": run.get("original_request"), "state": run.get("state"),
            "presentation_status": run.get("presentation_status"),
            "events": events, "trace_has_more": trace.get("has_more"),
        })
current_ids = {run["run_id"] for run in results}
results.extend(run for run in previous if run["run_id"] not in current_ids)
output.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps([{key: run[key] for key in ("request", "state", "presentation_status")} for run in results], indent=2))
