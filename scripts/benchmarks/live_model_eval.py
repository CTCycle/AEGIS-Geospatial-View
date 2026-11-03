"""Provider-aware live model evaluation with trace-level grading.

Runs the ``model_in_loop`` scenarios of the scenario matrix (and the holdout
set) against a running AEGIS backend with a chosen provider and model, then
grades every run from its public trace: route, tool sequence, termination,
evidence provenance, final-answer consistency, render verdict and false
success. Results are compared with a stored per-model baseline.

Two drivers share one grader:
  * default: a real Chromium (Playwright) drives the app UI, so the browser
    acknowledges map renders exactly as in production;
  * ``--no-render``: the realtime WebSocket protocol is driven directly. The
    run is cancelled once a map is prepared and the render verdict is recorded
    as UNVERIFIED, because no browser can acknowledge it.

Credentials are never read from arguments. Pass the provider key through the
environment variable named by ``--api-key-env`` (default ``AEGIS_EVAL_API_KEY``)
or rely on the key already stored by the app. When neither exists the run is
skipped with exit code 3.

Usage (from the repository root, backend already running):
    app/server/.venv/Scripts/python.exe scripts/benchmarks/live_model_eval.py \
        --provider opencode-go --model deepseek-v4.1-flash --no-render \
        --output-dir assets/QA/<folder>

Exit codes: 0 gate passed, 1 gate failed, 2 infrastructure error,
3 skipped (credentials missing).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))

from tests.agent_benchmark.live_grading import (  # noqa: E402
    DEFAULT_MAX_TURN_SECONDS,
    compare_to_baseline,
    grade_scenario,
    render_markdown,
)
from tests.agent_benchmark.scenario_matrix import load_scenario_matrix  # noqa: E402

BENCHMARK_DIR = ROOT / "app" / "tests" / "agent_benchmark"
MATRICES = {"main": "scenario_matrix.v1.json", "holdout": "scenario_matrix.holdout.v1.json"}
BASELINE_PATH = BENCHMARK_DIR / "live_eval_baseline.v1.json"
SUBPROTOCOL = "aegis.realtime.v1"
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})
TERMINAL_EVENTS = frozenset({"completed", "error", "cancelled", "clarification_needed"})
SKIPPED_EXIT = 3


class MissingCredentialsError(RuntimeError):
    """The provider has no usable API key in the environment or the app."""


###############################################################################
def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# -----------------------------------------------------------------------------
def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")


# -----------------------------------------------------------------------------
def select_scenarios(matrix_names: list[str], ids: set[str], limit: int | None) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for name in matrix_names:
        document = load_scenario_matrix(BENCHMARK_DIR / MATRICES[name])
        scenarios.extend(s for s in document["scenarios"] if s["lane"] == "model_in_loop")
    if ids:
        unknown = ids - {s["id"] for s in scenarios}
        if unknown:
            raise SystemExit(f"Unknown scenario ids: {sorted(unknown)}")
        scenarios = [s for s in scenarios if s["id"] in ids]
    return scenarios[:limit] if limit else scenarios


###############################################################################
class AppClient:
    """Thin REST client for the running backend."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.http = httpx.Client(base_url=f"{self.base_url}/api", timeout=30.0)

    # -------------------------------------------------------------------------
    def configure_model(self, provider: str, model: str, api_key_env: str) -> dict[str, Any]:
        """Select the evaluated model; return the previous settings for restoring."""

        previous = self.http.get("/chat/settings")
        previous.raise_for_status()
        before: dict[str, Any] = previous.json()
        patch: dict[str, Any] = {
            "active_provider_mode": "local" if provider == "ollama" else "cloud",
            "agent_model_provider": provider,
            "agent_model_name": model,
        }
        key = os.environ.get(api_key_env, "").strip()
        if key:
            patch["credentials"] = {provider: {"api_key": key}}
        response = self.http.patch("/chat/settings", json=patch)
        if response.status_code != 200:
            raise RuntimeError(f"Model selection rejected ({response.status_code}): {response.text[:300]}")
        current: dict[str, Any] = response.json()
        stored = current.get("credentials", {}).get(provider, {}).get("api_key")
        if provider != "ollama" and not stored:
            self.restore(before)
            raise MissingCredentialsError(f"No API key for provider '{provider}' (set ${api_key_env}).")
        return before

    # -------------------------------------------------------------------------
    def restore(self, before: dict[str, Any]) -> None:
        patch = {
            key: before.get(key)
            for key in ("active_provider_mode", "agent_model_provider", "agent_model_name")
            if before.get(key)
        }
        if patch:
            self.http.patch("/chat/settings", json=patch)

    # -------------------------------------------------------------------------
    def create_conversation(self) -> str:
        response = self.http.post("/conversations", json={"title": "live-eval"})
        response.raise_for_status()
        return str(response.json()["conversation_id"])

    # -------------------------------------------------------------------------
    def run_record(self, conversation_id: str, run_id: str) -> dict[str, Any]:
        """Fetch the run snapshot plus its complete internal trace."""

        snapshot = self.http.get(f"/conversations/{conversation_id}/runs/{run_id}")
        snapshot.raise_for_status()
        info: dict[str, Any] = snapshot.json()
        events: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 200, "include_internal": "true"}
            if cursor:
                params["cursor"] = cursor
            page = self.http.get(f"/conversations/{conversation_id}/runs/{run_id}/trace", params=params)
            page.raise_for_status()
            body: dict[str, Any] = page.json()
            events.extend(body["events"])
            cursor = body.get("next_cursor")
            if not body.get("has_more") or not cursor:
                break
        return {
            "run_id": run_id,
            "state": info.get("state"),
            "error_code": info.get("error_code"),
            "presentation_status": info.get("presentation_status"),
            "events": events,
        }

    # -------------------------------------------------------------------------
    def latest_run_ids(self, conversation_id: str, count: int) -> list[str]:
        response = self.http.get(f"/conversations/{conversation_id}")
        response.raise_for_status()
        recent = response.json().get("recent_runs") or []
        return [item["run_id"] for item in recent[:count]][::-1]


###############################################################################
def _message(kind: str, payload: dict[str, Any]) -> str:
    return json.dumps(
        {"protocol_version": 1, "type": kind, "message_id": uuid.uuid4().hex, "payload": payload}
    )


# -----------------------------------------------------------------------------
def run_turn_realtime(ws: Any, prompt: str, deadline: float, *, cancel_on_map: bool) -> dict[str, Any]:
    """Send one prompt over the realtime socket and wait for the run to settle."""

    ws.send(_message("run.start", {"message": prompt, "client_request_id": uuid.uuid4().hex}))
    started = time.monotonic()
    outcome: dict[str, Any] = {"run_id": None, "timed_out": False, "render_pending": False}
    cancelled = False
    while True:
        remaining = started + deadline - time.monotonic()
        if remaining <= 0:
            outcome["timed_out"] = True
            if outcome["run_id"] and not cancelled:
                ws.send(_message("run.cancel", {"run_id": outcome["run_id"], "reason": "eval deadline"}))
            break
        try:
            raw = ws.recv(timeout=min(remaining, 5.0))
        except TimeoutError:
            continue
        except ConnectionClosed as exc:
            raise RuntimeError(f"Realtime connection closed: {exc}") from exc
        message = json.loads(raw)
        payload = message.get("payload", {})
        if message["type"] == "heartbeat.ping":
            ws.send(_message("heartbeat.pong", {"nonce": payload.get("nonce")}))
        elif message["type"] == "run.ack":
            if not payload.get("accepted"):
                raise RuntimeError(f"run.start rejected: {payload}")
            outcome["run_id"] = payload["run_id"]
        elif message["type"] == "run.event":
            event_type = payload.get("type")
            if event_type == "map_prepared" and cancel_on_map and not cancelled:
                outcome["render_pending"] = True
                cancelled = True
                ws.send(_message("run.cancel", {"run_id": payload["run_id"], "reason": "render unverifiable"}))
            elif event_type in TERMINAL_EVENTS:
                break
    outcome["duration_seconds"] = time.monotonic() - started
    return outcome


# -----------------------------------------------------------------------------
def drive_scenario_realtime(client: AppClient, scenario: dict[str, Any]) -> list[dict[str, Any]]:
    prompts = [scenario["prompt"]] if "prompt" in scenario else list(scenario["turns"])
    deadline = float(scenario.get("max_turn_seconds") or DEFAULT_MAX_TURN_SECONDS)
    conversation_id = client.create_conversation()
    websocket_url = client.base_url.replace("http", "ws", 1) + f"/api/conversations/{conversation_id}/realtime"
    runs: list[dict[str, Any]] = []
    with connect(
        websocket_url, subprotocols=[SUBPROTOCOL], origin=client.base_url, max_size=None  # type: ignore[list-item]
    ) as ws:
        for prompt in prompts:
            outcome = run_turn_realtime(ws, prompt, deadline, cancel_on_map=True)
            if outcome["run_id"] is None:
                break
            time.sleep(1.0)  # let the final events persist
            record = client.run_record(conversation_id, outcome["run_id"])
            record.update(
                duration_seconds=outcome["duration_seconds"],
                timed_out=outcome["timed_out"],
                render_pending=outcome["render_pending"],
            )
            runs.append(record)
    return runs


###############################################################################
def drive_scenarios_browser(
    client: AppClient, scenarios: list[dict[str, Any]], ui_url: str, shots: Path
) -> dict[str, list[dict[str, Any]]]:
    """Drive the UI with Playwright so the browser acknowledges every render."""

    from playwright.sync_api import sync_playwright

    from tests.e2e.helpers.artifacts import write_snapshot

    shots.mkdir(parents=True, exist_ok=True)
    collected: dict[str, list[dict[str, Any]]] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for scenario in scenarios:
                page = browser.new_page()
                try:
                    collected[scenario["id"]] = _drive_scenario_browser(client, scenario, page, ui_url)
                    write_snapshot(page, shots, scenario["id"])
                finally:
                    page.close()
        finally:
            browser.close()
    return collected


# -----------------------------------------------------------------------------
def _drive_scenario_browser(client: AppClient, scenario: dict[str, Any], page: Any, ui_url: str) -> list[dict[str, Any]]:
    prompts = [scenario["prompt"]] if "prompt" in scenario else list(scenario["turns"])
    deadline = float(scenario.get("max_turn_seconds") or DEFAULT_MAX_TURN_SECONDS)
    page.goto(ui_url)
    page.get_by_role("button", name="Start new chat").click()
    runs: list[dict[str, Any]] = []
    conversation_id: str | None = None
    durations: list[float] = []
    timed_out = False
    for prompt in prompts:
        started = time.monotonic()
        page.get_by_label("Chat message").fill(prompt)
        page.get_by_role("button", name="Send message").click()
        known = {item["run_id"] for item in runs}
        while conversation_id is None and time.monotonic() - started < 30:
            conversation_id = _conversation_id(page)
            page.wait_for_timeout(500)
        if conversation_id is None:
            raise RuntimeError("The UI never created a conversation.")
        # The browser acknowledges renders while we poll the run state over REST.
        settled = False
        while time.monotonic() - started < deadline + 120:
            latest = client.latest_run_ids(conversation_id, len(runs) + 1)
            fresh = [rid for rid in latest if rid not in known]
            if fresh:
                snapshot = client.http.get(f"/conversations/{conversation_id}/runs/{fresh[-1]}").json()
                if snapshot.get("state") in TERMINAL_STATES:
                    runs.append({"run_id": fresh[-1]})
                    settled = True
                    break
            page.wait_for_timeout(1000)
        durations.append(time.monotonic() - started)
        timed_out = timed_out or not settled
        if not settled:
            break
    assert conversation_id is not None
    records = [client.run_record(conversation_id, item["run_id"]) for item in runs]
    for record, duration in zip(records, durations, strict=False):
        record.update(duration_seconds=duration, timed_out=duration > deadline + 90 or timed_out)
    return records


# -----------------------------------------------------------------------------
def _conversation_id(page: Any) -> str | None:
    raw = page.evaluate("() => window.sessionStorage.getItem('aegis:webapp-ui-state:v1')")
    try:
        state = json.loads(raw) if raw else {}
    except ValueError:
        return None
    value = state.get("chatPage", {}).get("chatPanel", {}).get("conversationId")
    return value if isinstance(value, str) and value.strip() else None


###############################################################################
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default=os.environ.get("AEGIS_EVAL_BASE_URL", "http://127.0.0.1:5013"))
    parser.add_argument("--ui-url", help="UI origin for browser mode (defaults to --base-url).")
    parser.add_argument("--matrix", choices=["main", "holdout", "both"], default="both")
    parser.add_argument("--scenario", default="", help="Comma-separated scenario ids.")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--no-render", action="store_true", help="Skip the browser; render is UNVERIFIED.")
    parser.add_argument("--api-key-env", default="AEGIS_EVAL_API_KEY")
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--write-baseline", action="store_true", help="Record this run as the model baseline.")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    names = ["main", "holdout"] if args.matrix == "both" else [args.matrix]
    scenarios = select_scenarios(names, {s for s in args.scenario.split(",") if s}, args.limit)
    model_key = f"{args.provider}/{args.model}"
    out = args.output_dir / _slug(model_key)
    out.mkdir(parents=True, exist_ok=True)
    render_mode = "none" if args.no_render else "browser"

    client = AppClient(args.base_url)
    try:
        previous = client.configure_model(args.provider, args.model, args.api_key_env)
    except MissingCredentialsError as exc:
        (out / "skipped.json").write_text(json.dumps({"model": model_key, "skipped": str(exc)}), encoding="utf-8")
        print(f"SKIPPED {model_key}: {exc}")
        return SKIPPED_EXIT
    except (httpx.HTTPError, RuntimeError) as exc:
        print(f"ERROR: cannot configure {model_key}: {exc}", file=sys.stderr)
        return 2

    try:
        if args.no_render:
            by_scenario: dict[str, list[dict[str, Any]]] = {}
            for scenario in scenarios:
                print(f"[{scenario['id']}] ...", flush=True)
                by_scenario[scenario["id"]] = drive_scenario_realtime(client, scenario)
        else:
            by_scenario = drive_scenarios_browser(client, scenarios, args.ui_url or args.base_url, out / "screenshots")
    finally:
        client.restore(previous)

    results = [grade_scenario(s, by_scenario.get(s["id"], []), render_mode=render_mode) for s in scenarios]
    baseline: dict[str, Any] = json.loads(args.baseline.read_text(encoding="utf-8")) if args.baseline.exists() else {}
    comparison = compare_to_baseline(model_key, results, baseline)

    traces = out / "traces"
    traces.mkdir(exist_ok=True)
    for scenario_id, runs in by_scenario.items():
        (traces / f"{scenario_id}.json").write_text(json.dumps(runs, indent=1, default=str), encoding="utf-8")
    report = {
        "model": model_key,
        "commit": _commit(),
        "render_mode": render_mode,
        "scenario_count": len(results),
        "comparison": comparison,
        "results": results,
    }
    (out / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "summary.md").write_text(render_markdown(model_key, results, comparison), encoding="utf-8")

    if args.write_baseline:
        baseline.setdefault("models", {})[model_key] = {
            "recorded_commit": report["commit"],
            "scenarios": {
                r["scenario_id"]: {"verdict": r["verdict"], **({"explanation": ""} if r["verdict"] == "fail" else {})}
                for r in results
            },
        }
        args.baseline.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        print(f"Baseline updated for {model_key}; document every failing scenario's explanation.")
    print((out / "summary.md").read_text(encoding="utf-8"))
    return 0 if comparison["gate_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
