from __future__ import annotations

from server.domain.agent.capability_route import AgentPhase, AgentRunState
from server.domain.agent.tool_result import ToolExecutionMetadata, ToolResult
from server.services.agent.completion import evidence_coordinates
from server.services.agent.final_answer_check import check_final_answer


###############################################################################
def test_claiming_two_markers_with_one_committed_is_flagged() -> None:
    violations = check_final_answer(
        "Both markers are now shown on the map.",
        target_names=["Rome"],
        layer_count=1, feature_count=1,
    )

    assert len(violations) == 1


###############################################################################
def test_naming_a_non_target_city_is_flagged() -> None:
    violations = check_final_answer(
        "The map now shows Paris with the weather layer.",
        target_names=["Rome"],
        other_places=["Paris"],
        layer_count=1, feature_count=1,
    )

    assert any("Paris" in item for item in violations)


###############################################################################
def test_completeness_wording_on_a_partial_result_is_flagged() -> None:
    assert check_final_answer(
        "The request was fully completed.",
        target_names=["Rome"],
        unmet=["render_verified"],
    )
    assert check_final_answer(
        "All done, everything is ready.",
        target_names=["Rome"],
        unmet=["render_verified"],
    )
    assert not check_final_answer(
        "Not completed: the forecast layer is missing.",
        target_names=["Rome"],
        unmet=["render_verified"],
    )


###############################################################################
def test_an_honest_answer_passes_unchanged() -> None:
    assert not check_final_answer(
        "The map shows Rome with one weather layer.",
        target_names=["Rome"],
        other_places=["Paris"],
        layer_count=1, feature_count=1,
    )


###############################################################################
def test_marker_claims_use_rendered_features_not_overlays() -> None:
    assert not check_final_answer(
        "The map shows 5 markers for the hospitals.",
        target_names=["Rome"],
        layer_count=1,
        feature_count=5,
    )
    assert not check_final_answer(
        "The map shows 5 markers.",
        target_names=["Rome"],
        layer_count=1,
        feature_count=None,
    )
    assert check_final_answer(
        "Two layers are visible.",
        target_names=["Rome"],
        layer_count=1,
        feature_count=5,
    )


###############################################################################
def test_completeness_wording_passes_when_the_limitation_is_disclosed() -> None:
    assert not check_final_answer(
        "I successfully retrieved data for Paris; Berlin data was unavailable.",
        target_names=["Paris", "Berlin"],
        unmet=["required_data_retrieved"],
    )
    assert not check_final_answer(
        "The request was fully completed.",
        target_names=["Rome"],
    )


###############################################################################
def test_claiming_an_unresolved_target_without_disclosure_is_flagged() -> None:
    claim = "The map now shows the Brandenburg Gate."
    assert check_final_answer(
        claim, target_names=["Berlin"], unresolved_targets=["Brandenburg Gate"]
    )
    assert not check_final_answer(
        "Berlin is shown; the Brandenburg Gate could not be resolved unambiguously.",
        target_names=["Berlin"],
        unresolved_targets=["Brandenburg Gate"],
    )


###############################################################################
def test_an_answer_about_two_places_must_name_both() -> None:
    required = [["Paris", "Paris, France"], ["Berlin", "Berlin, Germany"]]

    assert check_final_answer("The map now shows Paris.", target_names=["Paris", "Berlin"], required_targets=required)
    assert not check_final_answer("The map now shows Paris and Berlin.", target_names=["Paris", "Berlin"], required_targets=required)


###############################################################################
def test_map_content_is_not_described_when_no_map_was_verified() -> None:
    claim = "What's on the map: a thermal-anomaly overlay for Portugal."
    assert check_final_answer(claim, target_names=["Portugal"], map_rendered=False)
    assert not check_final_answer(claim, target_names=["Portugal"], map_rendered=None)
    assert not check_final_answer(
        "The map could not be shown, so no overlay was drawn.",
        target_names=["Portugal"], map_rendered=False,
    )


###############################################################################
def test_undelivered_obligations_must_be_disclosed() -> None:
    assert check_final_answer(
        "Lugano is 18.3 °C and Milan 19.4 °C.", target_names=["Lugano"],
        undelivered=["the requested map"],
    )
    assert not check_final_answer(
        "Lugano is 18.3 °C, but the map could not be confirmed.", target_names=["Lugano"],
        undelivered=["the requested map"],
    )


###############################################################################
def test_cited_values_must_match_the_evidence() -> None:
    evidence = [18.3, 19.4]
    assert check_final_answer("It is 21.7 °C in Lugano.", target_names=[], evidence_numbers=evidence)
    assert not check_final_answer("It is 18.3 °C in Lugano.", target_names=[], evidence_numbers=evidence)
    # A difference of two retrieved values is supported by them.
    assert not check_final_answer("Milan is 1.1 °C warmer.", target_names=[], evidence_numbers=evidence)
    assert check_final_answer("The strongest was magnitude 7.9.", target_names=[], evidence_numbers=[6.1, 5.4])


###############################################################################
def test_a_truncated_layer_must_be_disclosed() -> None:
    assert check_final_answer(
        "The map shows the earthquakes.", target_names=[], truncations=[(25, 205)],
    )
    assert not check_final_answer(
        "The map shows only the strongest 25 of the earthquakes.", target_names=[], truncations=[(25, 205)],
    )
    assert not check_final_answer(
        "There were 205 earthquakes; the map shows 25.", target_names=[], truncations=[(25, 205)],
    )


###############################################################################
def test_a_count_claim_about_the_map_may_not_exceed_what_rendered() -> None:
    kwargs = {"target_names": [], "feature_count": 25, "truncations": [(25, 205)]}
    assert check_final_answer("The map shows all 205 events.", **kwargs)
    assert not check_final_answer("The map shows only 25 of the 205 events.", **kwargs)
    assert not check_final_answer("USGS reported 205 events; the map shows 25.", **kwargs)


###############################################################################
def test_a_layer_removal_claim_needs_a_committed_layer_edit() -> None:
    claim = "The radar layer has been removed from the map."
    assert check_final_answer(claim, target_names=[], layer_edits=0)
    assert not check_final_answer(claim, target_names=[], layer_edits=1)
    assert not check_final_answer("No layer was removed.", target_names=[], layer_edits=0)
    assert not check_final_answer(claim, target_names=[])


###############################################################################
def test_a_comparison_answer_cites_each_targets_value_or_their_difference() -> None:
    groups = [[9.2, 8.8], [5.9, 6.1]]
    assert check_final_answer("Top results: wind forecast: precipitation 0", target_names=[], cite_groups=groups)
    assert check_final_answer("Vienna is warmer.", target_names=[], cite_groups=groups)
    assert not check_final_answer("Vienna is 9.2 °C and Prague 5.9 °C.", target_names=[], cite_groups=groups)
    assert not check_final_answer("Vienna is warmer by 3.3 °C.", target_names=[], cite_groups=groups)
    assert not check_final_answer("The strongest was M 6.1.", target_names=[], cite_groups=[[6.1, 4.0]])


###############################################################################
def test_a_rate_per_place_is_not_a_count_of_places() -> None:
    for text in ("Sampled at one point per city.", "Two samples for each city.", "One value every location."):
        assert not check_final_answer(text, target_names=[], feature_count=0)
    assert check_final_answer("Two cities are marked.", target_names=[], feature_count=1)


###############################################################################
def test_coordinates_of_inspected_records_are_supported_but_invented_ones_are_not() -> None:
    # S08-T2: the strongest event's position sits under record keys that
    # evidence_numbers skips, so a correct answer was replaced.
    record = {"latitude": 34.9677, "longitude": 142.1175, "magnitude": 6.1}
    state = AgentRunState(
        phase=AgentPhase.RECEIVE_REQUEST, request_id="r", conversation_id="c", user_message="Which one was strongest?"
    )
    state.tool_results.append(ToolResult(
        call_id="1", tool_name="inspect_evidence", status="success", summary="Inspected.",
        data={"result": {"statistics": {"magnitude": {"max": 6.1, "argmax": record}}}},
        metadata=ToolExecutionMetadata(duration_ms=1),
    ))
    coordinates = evidence_coordinates(state)

    def violations(text: str) -> list[str]:
        return check_final_answer(text, target_names=[], evidence_numbers=[6.1], coordinates=coordinates)

    assert not violations("M6.1 at 34.9677° N, 142.1175° E.")
    assert violations("M6.1 at 35.5° N, 142.1175° E.")
