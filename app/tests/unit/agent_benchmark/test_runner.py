from __future__ import annotations

import json
from pathlib import Path

from tests.agent_benchmark.runner import run_manifest


def test_scripted_fault_lane_is_provider_independent(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "id": "context-answerable-no-tool",
                        "lane": "scripted_fault",
                        "assertions": ["zero_tool_calls"],
                    },
                    {
                        "id": "timeout-recovery",
                        "lane": "scripted_fault",
                        "failure": "timeout",
                        "assertions": ["bounded_retry"],
                    },
                    {
                        "id": "invalid-geospatial-arguments",
                        "lane": "scripted_fault",
                        "failure": "invalid_coordinates_bounds_temporal",
                        "assertions": ["handler_not_called"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    bundle = run_manifest(
        manifest_path=manifest,
        output_dir=tmp_path / "out",
        base_url="http://127.0.0.1:1",
        lane="scripted_fault",
    )

    assert bundle["status"] == "passed"
    assert all(item["passed"] for item in bundle["results"])
    assert (tmp_path / "out" / "metrics.json").exists()
