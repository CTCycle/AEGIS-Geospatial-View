from __future__ import annotations

import json
from pathlib import Path

from tests.agent_benchmark.runner import evaluate_model_scenario, run_manifest


###############################################################################
def test_model_lane_evaluates_structured_tool_and_map_evidence() -> None:
    scenario = {"assertions": ["air_quality_tool", "rendered_map", "valid_arguments"]}
    traces = [
        {
            "status_code": 200,
            "tool_calls": [
                {
                    "name": "execute_geospatial_capability",
                    "arguments": {
                        "capability_id": "openmeteo_air_quality_forecast",
                        "arguments": {
                            "latitude": 47.3769,
                            "longitude": 8.5417,
                        },
                    },
                }
            ],
            "tool_results": [{"is_error": False}],
            "request_fingerprints": ["one"],
            "map_session": {
                "resolved_location": {"latitude": 47.3769, "longitude": 8.5417},
                "center": {"latitude": 47.3769, "longitude": 8.5417},
                "basemap": {"id": "osm_default"},
                "overlay_ids": ["openmeteo_air_quality_forecast"],
            },
            "response": {"assistant_message": "Map ready."},
        }
    ]

    evaluation = evaluate_model_scenario(scenario, traces)

    assert evaluation["passed"] is True
    assert evaluation["duplicate_tool_calls"] == 0


###############################################################################
def test_model_lane_scores_ambiguous_location_clarification() -> None:
    evaluation = evaluate_model_scenario(
        {"assertions": ["clarification_or_context_resolution"]},
        [
            {
                "status_code": 200,
                "tool_calls": [],
                "tool_results": [],
                "request_fingerprints": [],
                "response": {
                    "assistant_message": "Which specific location do you mean?",
                    "decision": {"plan": {"state": "clarify"}},
                    "turn_contract": {},
                },
            }
        ],
    )

    assert evaluation["passed"] is True


###############################################################################
def test_model_lane_evaluates_matrix_properties_without_exact_answer_matching() -> None:
    evaluation = evaluate_model_scenario(
        {
            "expected": {
                "task_classes": ["map_search"],
                "capability_families": ["weather"],
                "clarification": "not_required",
                "minimum_tool_count": 1,
                "rendering_types": ["map", "text"],
                "provenance_required": True,
                "fabrication_forbidden": True,
            }
        },
        [
            {
                "status_code": 200,
                "tool_calls": [
                    {
                        "name": "execute_geospatial_capability",
                        "arguments": {
                            "capability_id": "openmeteo_weather_forecast",
                            "arguments": {"latitude": 41.9028, "longitude": 12.4964},
                        },
                    }
                ],
                "tool_results": [
                    {
                        "is_error": False,
                        "provenance": {
                            "provider": "open-meteo",
                            "fetched_at": "2026-09-01T10:00:00Z",
                        },
                    }
                ],
                "response": {
                    "assistant_message": "The verified weather result is ready.",
                    "turn_contract": {
                        "task_class": "map_search",
                        "capability_limitations": [],
                    },
                    "decision": {"plan": {"state": "execute"}},
                },
                "map_session": {
                    "resolved_location": {
                        "latitude": 41.9028,
                        "longitude": 12.4964,
                    },
                    "center": {"latitude": 41.9028, "longitude": 12.4964},
                    "basemap": {"id": "osm_default"},
                },
                "request_fingerprints": ["weather-1"],
            }
        ],
    )

    assert evaluation["passed"] is True
    assert all(item["passed"] for item in evaluation["assertions"])


###############################################################################
def test_model_lane_rejects_unexplained_unbacked_answer() -> None:
    evaluation = evaluate_model_scenario(
        {
            "expected": {
                "task_classes": ["direct_query"],
                "capability_families": [],
                "clarification": "not_required",
                "minimum_tool_count": 0,
                "rendering_types": ["text"],
                "provenance_required": False,
                "fabrication_forbidden": True,
            }
        },
        [
            {
                "status_code": 200,
                "tool_calls": [],
                "tool_results": [],
                "response": {
                    "assistant_message": "The crime rate is 12.4 per 1,000 people.",
                    "turn_contract": {"task_class": "direct_query"},
                    "decision": {"plan": {"state": "execute"}},
                },
                "request_fingerprints": [],
            }
        ],
    )

    grounding = next(
        item
        for item in evaluation["assertions"]
        if item["name"] == "expected_grounding"
    )
    assert grounding["passed"] is False
    assert evaluation["passed"] is False


###############################################################################
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
