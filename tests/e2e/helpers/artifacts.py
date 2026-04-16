from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_test_artifact_dirs(artifact_root: Path, test_id: str) -> dict[str, Path]:
    screenshot_dir = artifact_root / "screenshots" / test_id
    http_dir = artifact_root / "http" / test_id
    logs_dir = artifact_root / "logs"
    reports_dir = artifact_root / "reports"
    for path in (screenshot_dir, http_dir, logs_dir, reports_dir):
        path.mkdir(parents=True, exist_ok=True)
    return {
        "screenshots": screenshot_dir,
        "http": http_dir,
        "logs": logs_dir,
        "reports": reports_dir,
    }


def write_snapshot(page: Any, screenshot_dir: Path, name: str) -> Path:
    filename = name if name.lower().endswith(".png") else f"{name}.png"
    target = screenshot_dir / filename
    page.screenshot(path=str(target), full_page=True)
    return target


def write_http_capture(http_dir: Path, name: str, request_body: Any, response_body: Any) -> Path:
    target = http_dir / f"{name}.json"
    target.write_text(
        json.dumps(
            {
                "request": request_body,
                "response": response_body,
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    return target


def write_log_tail(logs_dir: Path, test_id: str, log_tail: str) -> Path:
    target = logs_dir / f"{test_id}.backend.tail.log"
    target.write_text(log_tail or "", encoding="utf-8")
    return target


def write_report(
    reports_dir: Path,
    test_id: str,
    prompts: list[str],
    assertions: list[str],
    backend_log_status: str,
) -> Path:
    target = reports_dir / f"{test_id}.md"
    lines = [f"# {test_id}", "", "## Prompts sent"]
    if prompts:
        lines.extend([f"- {prompt}" for prompt in prompts])
    else:
        lines.append("- None")
    lines.extend(["", "## Key UI assertions"])
    if assertions:
        lines.extend([f"- {assertion}" for assertion in assertions])
    else:
        lines.append("- None")
    lines.extend(["", "## Backend log tail", f"- {backend_log_status}", ""])
    target.write_text("\n".join(lines), encoding="utf-8")
    return target
