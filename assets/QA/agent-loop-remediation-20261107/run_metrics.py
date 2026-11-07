"""Print one metrics line per agent run created after a given UTC timestamp."""
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime

DB = sys.argv[1]
SINCE = sys.argv[2]
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
runs = con.execute(
    "select id, conversation_id, original_request, state, presentation_status, created_at, completed_at"
    " from agent_runs where created_at >= ? order by created_at",
    (SINCE,),
).fetchall()
for rid, conv, req, state, pres, created, completed in runs:
    calls = tin = tout = tools = maps = 0
    failed: list[str] = []
    providers: set[tuple[str, str]] = set()
    phases: Counter[str] = Counter()
    phase_tokens: Counter[str] = Counter()
    for etype, payload in con.execute(
        "select type, payload_json from agent_run_events where run_id=? order by sequence", (rid,)
    ):
        data = json.loads(payload)
        if etype == "context_usage":
            usage = data.get("context_usage") or {}
            calls += 1
            tokens = usage.get("reported_input_tokens") or usage.get("estimated_input_tokens") or 0
            tin += tokens
            tout += usage.get("reported_output_tokens") or 0
            phase = usage.get("call_phase") or data.get("call_phase") or "?"
            phases[phase] += 1
            phase_tokens[phase] += tokens
            providers.add((str(usage.get("selected_provider") or usage.get("provider")), str(usage.get("selected_model") or usage.get("model"))))
        elif etype in {"tool_completed", "tool_failed"}:
            tools += 1
            if data.get("status") not in (None, "success"):
                failed.append(f"{data.get('tool_name')}:{data.get('error_code') or data.get('status')}")
        elif etype == "map_prepared":
            maps += 1
    dur = "?"
    if completed:
        dur = f"{(datetime.fromisoformat(completed) - datetime.fromisoformat(created)).total_seconds():.0f}s"
    phase_text = ",".join(f"{k}={phases[k]}/{phase_tokens[k]}" for k in sorted(phases))
    print(
        f"{conv[5:11]} {rid[4:10]} {state} {pres} dur={dur} calls={calls} tok={tin}/{tout} tools={tools}"
        f" maps={maps} failed={failed} phases=[{phase_text}] prov={sorted(providers)} | {req[:45]}"
    )
