from __future__ import annotations

import json
from pathlib import Path

from tests.agent_benchmark.runner import (
    _live_provider_block_reason,
    evaluate_model_scenario,
    run_manifest,
)


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
def test_model_lane_accepts_first_class_location_provider_evidence() -> None:
    evaluation = evaluate_model_scenario(
        {
            "expected": {
                "task_classes": ["map_search"],
                "capability_families": ["location"],
                "clarification": "not_required",
                "minimum_tool_count": 1,
                "rendering_types": ["map"],
                "provenance_required": True,
                "fabrication_forbidden": True,
            }
        },
        [
            {
                "status_code": 200,
                "tool_calls": [],
                "tool_results": [],
                "provider_events": [
                    {
                        "kind": "location_resolution",
                        "capability_id": "location",
                        "provider": "nominatim",
                        "source_url": "https://nominatim.openstreetmap.org/search",
                        "fetched_at": "2026-09-01T10:00:00Z",
                    }
                ],
                "response": {
                    "assistant_message": "Zurich is centered on the map.",
                    "turn_contract": {
                        "task_class": "map_search",
                        "capability_limitations": [],
                    },
                    "decision": {"plan": {"state": "map_search"}},
                },
                "map_session": {
                    "resolved_location": {
                        "latitude": 47.3744,
                        "longitude": 8.5410,
                    },
                    "center": {"latitude": 47.3744, "longitude": 8.5410},
                    "basemap": {"id": "esri_world_imagery"},
                },
                "request_fingerprints": [],
            }
        ],
    )

    assert evaluation["passed"] is True
    assert evaluation["tool_calls"] == 0
    assert evaluation["provider_events"] == 1
    assert evaluation["execution_evidence"] == 1


###############################################################################
def test_model_lane_accepts_explicit_coordinate_grounding_without_provider_call() -> None:
    evaluation = evaluate_model_scenario(
        {
            "expected": {
                "task_classes": ["map_search"],
                "capability_families": ["location"],
                "clarification": "not_required",
                "minimum_tool_count": 1,
                "rendering_types": ["map"],
                "provenance_required": True,
                "fabrication_forbidden": True,
            }
        },
        [
            {
                "status_code": 200,
                "prompt": "Center the map at 35.6895, 139.6917.",
                "tool_calls": [],
                "tool_results": [],
                "provider_events": [],
                "response": {
                    "assistant_message": "The map is centered on the requested coordinates.",
                    "turn_contract": {
                        "user_text": "Center the map at 35.6895, 139.6917.",
                        "task_class": "map_search",
                        "location_signals": [
                            {
                                "signal_type": "coordinates",
                                "raw_value": "35.6895, 139.6917",
                                "normalized_value": "35.6895, 139.6917",
                                "latitude": 35.6895,
                                "longitude": 139.6917,
                            }
                        ],
                        "capability_limitations": [],
                    },
                    "decision": {"plan": {"state": "map_search"}},
                },
                "map_session": {
                    "resolved_location": {
                        "label": "35.6895, 139.6917",
                        "latitude": 35.6895,
                        "longitude": 139.6917,
                        "location_type": "coordinates",
                        "source": "model",
                    },
                    "center": {"latitude": 35.6895, "longitude": 139.6917},
                    "basemap": {"id": "esri_world_imagery"},
                },
                "request_fingerprints": [],
            }
        ],
    )

    assert evaluation["passed"] is True
    assert evaluation["provider_events"] == 0
    assert evaluation["execution_evidence"] == 1


###############################################################################
def test_model_lane_does_not_count_model_invented_coordinates_as_grounding() -> None:
    evaluation = evaluate_model_scenario(
        {
            "assertions": ["valid_arguments"],
            "expected": {
                "task_classes": ["map_search"],
                "capability_families": ["location"],
                "clarification": "not_required",
                "minimum_tool_count": 1,
                "rendering_types": ["map"],
                "provenance_required": True,
                "fabrication_forbidden": True,
            },
        },
        [
            {
                "status_code": 200,
                "prompt": "Center the map on an unspecified place.",
                "tool_calls": [],
                "tool_results": [],
                "provider_events": [],
                "response": {
                    "assistant_message": "The map is centered.",
                    "turn_contract": {
                        "user_text": "Center the map on an unspecified place.",
                        "task_class": "map_search",
                        "location_signals": [
                            {
                                "signal_type": "coordinates",
                                "raw_value": "35.6895, 139.6917",
                                "normalized_value": "35.6895, 139.6917",
                                "latitude": 35.6895,
                                "longitude": 139.6917,
                            }
                        ],
                        "capability_limitations": [],
                    },
                    "decision": {"plan": {"state": "map_search"}},
                },
                "map_session": {
                    "resolved_location": {
                        "label": "35.6895, 139.6917",
                        "latitude": 35.6895,
                        "longitude": 139.6917,
                        "location_type": "coordinates",
                    },
                    "center": {"latitude": 35.6895, "longitude": 139.6917},
                    "basemap": {"id": "esri_world_imagery"},
                },
                "request_fingerprints": [],
            }
        ],
    )

    assert evaluation["passed"] is False
    assert any(
        item["name"] == "valid_arguments" and not item["passed"]
        for item in evaluation["assertions"]
    )


###############################################################################
def test_model_lane_accepts_safe_clarification_for_allowed_location_outcome() -> None:
    evaluation = evaluate_model_scenario(
        {
            "expected": {
                "task_classes": ["map_search"],
                "capability_families": ["location"],
                "clarification": "allowed",
                "minimum_tool_count": 1,
                "rendering_types": ["map", "point"],
                "provenance_required": True,
                "fabrication_forbidden": True,
            },
            "assertions": ["valid_arguments", "location_or_clarification"],
            "invariants": ["location_target_consistency"],
        },
        [
            {
                "status_code": 200,
                "response": {
                    "assistant_message": "Please provide a more specific location.",
                    "turn_contract": {
                        "task_class": "map_search",
                        "clarification_plan": {
                            "state": "clarify",
                            "question": "Which site do you mean?",
                        },
                    },
                    "decision": {
                        "plan": {"state": "clarify"},
                        "clarification": {"question": "Which site do you mean?"},
                    },
                    "operation": {
                        "kind": "clarification",
                        "status": "partial",
                    },
                },
                "map_session": None,
                "tool_calls": [],
                "tool_results": [],
                "provider_events": [],
                "request_fingerprints": [],
            }
        ],
    )

    assert evaluation["passed"] is True


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
def test_model_lane_checks_context_peak_and_phase_invariants() -> None:
    usage = {
        "estimated_input_tokens": 180,
        "reported_input_tokens": 200,
        "reported_output_tokens": 5,
        "selected_context_window": 4096,
        "usage_percent": 6.5,
        "usable_prompt_budget_tokens": 3072,
        "usage_source": "provider_reported",
        "peak_request_tokens": 700,
        "total_input_tokens": 1000,
        "total_output_tokens": 23,
        "phases": {
            "parser": {
                "estimated_input_tokens": 90,
                "reported_input_tokens": 100,
                "reported_output_tokens": 7,
                "usage_source": "provider_reported",
            },
            "native_loop": {
                "estimated_input_tokens": 500,
                "reported_input_tokens": 700,
                "reported_output_tokens": 11,
                "usage_source": "provider_reported",
            },
            "synthesis": {
                "estimated_input_tokens": 180,
                "reported_input_tokens": 200,
                "reported_output_tokens": 5,
                "usage_source": "provider_reported",
            },
        },
    }
    evaluation = evaluate_model_scenario(
        {"invariants": ["context_usage_invariants"]},
        [{"status_code": 200, "response": {"context_usage": usage}}],
    )

    assert evaluation["passed"] is True


###############################################################################
def test_model_lane_rejects_unknown_cap_determinate_percentage() -> None:
    evaluation = evaluate_model_scenario(
        {"invariants": ["context_usage_invariants"]},
        [
            {
                "status_code": 200,
                "response": {
                    "context_usage": {
                        "estimated_input_tokens": 30,
                        "selected_context_window": None,
                        "usage_percent": 4.0,
                        "usage_source": "estimated",
                    }
                },
            }
        ],
    )

    assert evaluation["passed"] is False


###############################################################################
def test_model_lane_rejects_parent_downgrade_and_center_mismatch() -> None:
    evaluation = evaluate_model_scenario(
        {
            "dimensions": {"geographic_scale": "city"},
            "invariants": ["location_target_consistency"],
        },
        [
            {
                "status_code": 200,
                "map_session": {
                    "resolved_location": {
                        "label": "Example Country",
                        "latitude": 40.0,
                        "longitude": 10.0,
                        "location_type": "country",
                    },
                    "center": {"latitude": 40.1, "longitude": 10.0},
                    "basemap": {"id": "osm"},
                },
                "response": {},
            }
        ],
    )

    assert evaluation["passed"] is False


###############################################################################
def test_model_lane_requires_categorized_failures_and_no_false_success() -> None:
    evaluation = evaluate_model_scenario(
        {
            "invariants": ["categorized_failures", "no_false_success"],
        },
        [
            {
                "status_code": 200,
                "response": {
                    "operation": {
                        "kind": "map_session",
                        "status": "failed",
                        "failure_category": "provider_api",
                    }
                },
            }
        ],
    )

    assert evaluation["passed"] is True


###############################################################################
def test_model_lane_checks_ambiguous_clarification_and_deadline() -> None:
    evaluation = evaluate_model_scenario(
        {
            "max_turn_seconds": 5,
            "expected": {
                "task_classes": ["map_search", "unclear"],
                "capability_families": [],
                "clarification": "required",
                "minimum_tool_count": 0,
                "rendering_types": ["text", "none"],
                "provenance_required": False,
                "fabrication_forbidden": True,
            },
            "invariants": ["clarification_correctness", "deadline_compliance"],
        },
        [
            {
                "status_code": 200,
                "duration_seconds": 1.25,
                "map_session": None,
                "response": {
                    "turn_contract": {"task_class": "unclear"},
                    "decision": {
                        "plan": {"state": "clarify"},
                        "clarification": {
                            "question": "Which location do you mean?"
                        },
                    }
                },
            }
        ],
    )

    assert evaluation["passed"] is True


###############################################################################
def test_live_lane_blocks_provider_failure_without_blocking_verified_map_success() -> None:
    assert _live_provider_block_reason(
        {
            "status_code": 200,
            "response": {
                "operation": {
                    "kind": "error",
                    "status": "failed",
                    "failure_category": "provider_api",
                }
            },
        }
    ) == "provider_unavailable"
    assert _live_provider_block_reason(
        {
            "status_code": 200,
            "response": {
                "operation": {
                    "kind": "map_session",
                    "status": "success",
                },
                "map_session": {"resolved_location": {"latitude": 1, "longitude": 2}},
            },
        }
    ) is None


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
