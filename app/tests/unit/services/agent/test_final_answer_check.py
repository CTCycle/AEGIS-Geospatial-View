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
