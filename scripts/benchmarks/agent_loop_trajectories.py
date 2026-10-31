"""Deterministic agent-loop trajectory benchmark.

Replays the scripted scenarios in ``app/tests/agent_benchmark/trajectories.py``
through the real agent loop and reports model calls, tool calls, iterations,
estimated input tokens per model call and local wall time. Results are printed
as JSON; pass ``--output`` to save them, or ``--write-baseline`` to refresh the
gate baseline after a deliberate change.

Usage (from the repository root):
    app/server/.venv/Scripts/python.exe scripts/benchmarks/agent_loop_trajectories.py \
        --output assets/QA/<folder>/agent-loop-trajectories-<label>.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))

from tests.agent_benchmark.trajectories import run_all  # noqa: E402

BASELINE_PATH = ROOT / "app" / "tests" / "agent_benchmark" / "trajectory_baseline.v1.json"

###############################################################################
def _commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"

###############################################################################
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()

    results = asyncio.run(run_all())
    report = {
        "commit": _commit(),
        "python": platform.python_version(),
        "scenarios": results,
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    if args.write_baseline:
        baseline = {
            "version": 1,
            "scenarios": {
                item["scenario_id"]: {
                    "termination_reason": item["termination_reason"],
                    "model_calls": item["model_calls"],
                    "total_estimated_input_tokens": item["total_estimated_input_tokens"],
                }
                for item in results
            },
        }
        BASELINE_PATH.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
