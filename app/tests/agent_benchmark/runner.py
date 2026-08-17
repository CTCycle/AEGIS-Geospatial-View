from __future__ import annotations

"""Run the versioned scenario manifest against a running AEGIS backend.

The runner intentionally does not select a provider or model.  The backend's
configured model is recorded in the output and a structured-output preflight
failure produces a blocked lane rather than silently substituting a model.
"""

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx


def _json_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {"status_code": response.status_code, "text": response.text[:1000]}
    return payload if isinstance(payload, dict) else {"value": payload}


def _fingerprint(tool: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(tool, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def run_manifest(
    *,
    manifest_path: Path,
    output_dir: Path,
    base_url: str,
    lane: str | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    scenarios = [
        scenario
        for scenario in manifest["scenarios"]
        if lane is None or scenario.get("lane") == lane
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(base_url=base_url.rstrip("/"), timeout=180.0)
    started = time.perf_counter()
    health = client.get("/api/health")
    results: list[dict[str, Any]] = []
    for scenario in scenarios:
        conversation_response = client.post(
            "/api/conversations",
            json={"title": f"benchmark {scenario['id']}"},
        )
        conversation_payload = _json_response(conversation_response)
        conversation_id = conversation_payload.get("conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id:
            conversation_id = f"benchmark-{uuid4().hex}"
        turns = scenario.get("turns") or [scenario.get("prompt", "")]
        trace: list[dict[str, Any]] = []
        scenario_started = time.perf_counter()
        for turn in turns:
            response = client.post(
                "/api/chat/turn",
                json={"conversation_id": conversation_id, "message": turn},
            )
            payload = _json_response(response)
            tool_payload = payload.get("tool_payload")
            tool_calls = tool_payload.get("tool_calls", []) if isinstance(tool_payload, dict) else []
            trace.append(
                {
                    "prompt": turn,
                    "status_code": response.status_code,
                    "tool_calls": tool_calls,
                    "tool_results": tool_payload.get("tool_results", [])
                    if isinstance(tool_payload, dict)
                    else [],
                    "response": payload,
                    "map_session": payload.get("map_session"),
                    "request_fingerprints": [_fingerprint(item) for item in tool_calls if isinstance(item, dict)],
                }
            )
        results.append(
            {
                "scenario_id": scenario["id"],
                "conversation_id": conversation_id,
                "elapsed_seconds": time.perf_counter() - scenario_started,
                "turns": trace,
                "status": "blocked"
                if any(
                    item["status_code"] == 503
                    or "could not perform structured extraction" in str(item["response"])
                    or "credentials are not configured" in str(item["response"])
                    for item in trace
                )
                else "recorded",
            }
        )
    bundle = {
        "manifest": str(manifest_path),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "health": {"status_code": health.status_code, "payload": _json_response(health)},
        "elapsed_seconds": time.perf_counter() - started,
        "results": results,
    }
    (output_dir / "benchmark.json").write_text(
        json.dumps(bundle, indent=2, ensure_ascii=True, default=str), encoding="utf-8"
    )
    (output_dir / "trace.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=True, default=str) for item in results) + "\n",
        encoding="utf-8",
    )
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default=os.environ.get("AEGIS_BASE_URL", "http://127.0.0.1:7059"))
    parser.add_argument("--lane", choices=["model_in_loop", "scripted_fault", "live_smoke"])
    args = parser.parse_args()
    run_manifest(
        manifest_path=args.manifest,
        output_dir=args.output,
        base_url=args.base_url,
        lane=args.lane,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
