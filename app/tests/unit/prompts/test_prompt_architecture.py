from __future__ import annotations

import ast
from importlib import import_module
from pathlib import Path
from string import Formatter

import pytest

from server.domain.agent.extraction_schemas import LLMParserExtraction
from server.prompts.agent import (
    NATIVE_AGENT_CONTEXT_TEMPLATE,
    WORKING_STATE_TEMPLATE,
    build_native_agent_messages,
    build_native_agent_system_prompt,
    build_working_state_message,
)
from server.prompts.common import (
    GROUNDING_REQUIREMENTS,
    INTERNAL_INFORMATION_RESTRICTIONS,
    SUPPORTED_AEGIS_SCOPE,
    UNCERTAINTY_RULES,
)
from server.prompts.context import (
    COMPACTED_HISTORY_SUMMARY_TEMPLATE,
    build_compacted_history_summary,
)
from server.prompts.parser import (
    PARSER_SCHEMA_CORRECTION,
    PARSER_SYSTEM_PROMPT,
    build_parser_prompt,
)
from server.prompts.providers import (
    DEEPSEEK_JSON_SCHEMA_TEMPLATE,
    OLLAMA_TOOL_CAPABILITY_PROBE_PROMPT,
    build_deepseek_json_schema_instruction,
)
from server.prompts.response import (
    GROUNDED_RESPONSE_SYSTEM_PROMPT,
    VERIFIED_EVIDENCE_USER_TEMPLATE,
    build_response_prompt,
    build_verified_evidence_prompt,
)
from server.services.llm.context_budget import (
    compute_context_usage,
    estimate_message_tokens,
)
from server.services.llm.types import LLMRequest

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SERVER_ROOT = REPOSITORY_ROOT / "app" / "server"
PROMPTS_ROOT = SERVER_ROOT / "prompts"
PROMPT_MODULES = (
    "server.prompts",
    "server.prompts.common",
    "server.prompts.parser",
    "server.prompts.agent",
    "server.prompts.response",
    "server.prompts.context",
    "server.prompts.providers",
)


###############################################################################
@pytest.mark.parametrize("module_name", PROMPT_MODULES)
def test_prompt_modules_are_importable(module_name: str) -> None:
    assert import_module(module_name)


###############################################################################
def _template_fields(template: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name is not None
    }


###############################################################################
@pytest.mark.parametrize(
    ("template", "expected_fields"),
    [
        (
            NATIVE_AGENT_CONTEXT_TEMPLATE,
            {
                "active_instructions",
                "memory_snapshot",
                "parsed_request",
                "policy_constraints",
                "task_snapshot",
            },
        ),
        (WORKING_STATE_TEMPLATE, {"state_json"}),
        (VERIFIED_EVIDENCE_USER_TEMPLATE, {"evidence_json"}),
        (DEEPSEEK_JSON_SCHEMA_TEMPLATE, {"schema_json"}),
        (COMPACTED_HISTORY_SUMMARY_TEMPLATE, {"summary"}),
    ],
)
def test_prompt_templates_expose_only_their_intended_variables(
    template: str,
    expected_fields: set[str],
) -> None:
    assert _template_fields(template) == expected_fields


###############################################################################
def test_prompt_builders_substitute_every_template_variable() -> None:
    parser_prompt = build_parser_prompt(schema_correction=True)
    native_messages = build_native_agent_messages(
        turn_contract=LLMParserExtraction(),
        memory_snapshot={"active_location": {"label": "Rome"}},
        constraints={"allowed_tool_names": ["list_geospatial_capabilities"]},
        active_instructions=[{"text": "Prefer concise answers."}],
        task_snapshot={"status": "routed"},
    )
    working_state = build_working_state_message(
        parsed_request={"task_class": "map_search"},
        map_state={},
        policy_constraints={},
        completed_tool_results=[],
    )
    response_messages = build_response_prompt(
        {"verified_outcome": {"status": "success"}}
    )

    assert "{schema_correction}" not in parser_prompt
    assert "{parsed_request}" not in native_messages[1]["content"]
    assert "{active_instructions}" not in native_messages[1]["content"]
    assert "{state_json}" not in working_state["content"]
    assert "{evidence_json}" not in response_messages[1]["content"]
    assert "{schema_json}" not in build_deepseek_json_schema_instruction(
        {"type": "object"}
    )
    assert "{summary}" not in build_compacted_history_summary("older turn")
    assert OLLAMA_TOOL_CAPABILITY_PROBE_PROMPT == (
        "Call the aegis_tool_probe tool with empty arguments."
    )
    assert build_verified_evidence_prompt({"verified": True}).startswith(
        "Write the final response using only this verified evidence:"
    )


###############################################################################
def _prompt_constant_assignments(tree: ast.Module) -> list[tuple[str, ast.expr]]:
    assignments: list[tuple[str, ast.expr]] = []
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            targets = statement.targets
            value = statement.value
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
            value = statement.value
        else:
            continue
        if value is None:
            continue
        for target in targets:
            if not isinstance(target, ast.Name) or not target.id.isupper():
                continue
            if any(
                marker in target.id
                for marker in (
                    "PROMPT",
                    "TEMPLATE",
                    "FRAGMENT",
                    "RULE",
                    "SCOPE",
                    "RESTRICTION",
                )
            ):
                assignments.append((target.id, value))
    return assignments


###############################################################################
def test_prompt_constants_are_literal_module_level_strings() -> None:
    for path in PROMPTS_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, value in _prompt_constant_assignments(tree):
            assert isinstance(value, ast.Constant), f"{path.name}:{name} is not literal"
            assert isinstance(value.value, str), f"{path.name}:{name} is not a string"


###############################################################################
def test_backend_has_no_obsolete_prompt_api_references() -> None:
    obsolete_markers = (
        "server.services.llm." + "prompts",
        "get_agent_" + "extraction_prompt",
        "get_agent_" + "enrichment_prompt",
        "get_agent_" + "decision_system_prompt",
        "get_agent_" + "response_prompt",
        "get_parser_" + "system_prompt",
        "prompt_" + "within_budget",
    )
    for path in SERVER_ROOT.rglob("*.py"):
        if PROMPTS_ROOT in path.parents:
            continue
        contents = path.read_text(encoding="utf-8")
        assert not any(marker in contents for marker in obsolete_markers), path


###############################################################################
def test_model_instructions_are_not_fragmented_outside_prompt_package() -> None:
    markers = (
        "You are the AEGIS",
        "SCHEMA CORRECTION",
        "WORKING_STATE",
        "Write the final response using only",
        "Return a JSON object that matches this JSON Schema",
        "Call the aegis_tool_probe tool with empty arguments.",
    )
    findings = {
        f"{path}:{marker}"
        for path in SERVER_ROOT.rglob("*.py")
        if PROMPTS_ROOT not in path.parents
        for marker in markers
        if marker in path.read_text(encoding="utf-8")
    }
    assert not findings


###############################################################################
def test_composed_prompts_include_shared_rules_once() -> None:
    parser_prompt = build_parser_prompt()
    native_prompt = build_native_agent_system_prompt()
    response_prompt = build_response_prompt({})[0]["content"]

    for prompt in (parser_prompt, native_prompt, response_prompt):
        assert prompt.count(SUPPORTED_AEGIS_SCOPE) == 1
        assert prompt.count(UNCERTAINTY_RULES) == 1
        assert prompt.count(INTERNAL_INFORMATION_RESTRICTIONS) == 1
    for prompt in (native_prompt, response_prompt):
        assert prompt.count(GROUNDING_REQUIREMENTS) == 1
    assert (
        build_parser_prompt(schema_correction=True).count(PARSER_SCHEMA_CORRECTION) == 1
    )
    assert PARSER_SYSTEM_PROMPT in parser_prompt
    assert GROUNDED_RESPONSE_SYSTEM_PROMPT in response_prompt


###############################################################################
def test_prompt_budget_uses_runtime_context_budget_estimator() -> None:
    messages = build_response_prompt({"verified_outcome": {"status": "success"}})
    request = LLMRequest(model="gpt-4.1", provider="openai", messages=messages)
    usage = compute_context_usage(request, provider="openai")

    assert usage.estimated_input_tokens == estimate_message_tokens(messages)
    assert usage.estimated_input_tokens > 0
