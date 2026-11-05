from __future__ import annotations

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
