from server.prompts.capability_route import build_capability_route_prompt


def test_route_prompt_owns_route_scope_without_execution_arguments() -> None:
    prompt = build_capability_route_prompt()

    assert "route_request" in prompt
    assert "capability_queries" in prompt
    assert "coordinates" in prompt
    assert "radii" in prompt
    assert "provider arguments" in prompt
    assert "execute a provider" in prompt
