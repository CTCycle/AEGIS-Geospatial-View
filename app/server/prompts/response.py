"""Prompt declarations and builders for grounded response synthesis."""

from __future__ import annotations

import json
from typing import Any

from server.prompts.common import (
    GROUNDING_REQUIREMENTS,
    INTERNAL_INFORMATION_RESTRICTIONS,
    SUPPORTED_AEGIS_SCOPE,
    UNCERTAINTY_RULES,
)

GROUNDED_RESPONSE_SYSTEM_PROMPT = (
    "You create one concise user-facing AEGIS response from the verified "
    "application evidence supplied in the user message.\n\n"
    "Response rules:\n"
    "1. Use only the supplied verified evidence; never invent successful "
    "execution, measurements, sources, recommendations, or missing values.\n"
    "2. Distinguish confirmed results from metadata-only state. An evidence "
    "item with rendered=false or status=metadata_only is context or setup, not "
    "a live rendered map layer.\n"
    "3. Preserve warnings, partial results, and unresolved source conflicts.\n"
    "4. Request clarification only when the evidence identifies a blocking "
    "ambiguity, and ask one focused question.\n"
    "5. Acknowledge insufficient or unavailable evidence instead of filling "
    "the gap.\n"
    "6. Answer general questions and clarification outcomes from their supplied "
    "evidence without assuming that an active map search occurred.\n"
    "7. Use human-readable labels and coordinates when verified; do not expose "
    "raw payloads or internal field names.\n"
    "8. Return Markdown suitable for direct display. Do not add greetings, "
    "progress claims, or a second answer."
)

VERIFIED_EVIDENCE_USER_TEMPLATE = (
    "Write the final response using only this verified evidence:\n{evidence_json}"
)

###############################################################################
def build_grounded_response_system_prompt() -> str:
    return "\n\n".join(
        [
            GROUNDED_RESPONSE_SYSTEM_PROMPT,
            SUPPORTED_AEGIS_SCOPE,
            GROUNDING_REQUIREMENTS,
            UNCERTAINTY_RULES,
            INTERNAL_INFORMATION_RESTRICTIONS,
        ]
    )

###############################################################################
def build_verified_evidence_prompt(evidence: Any) -> str:
    return VERIFIED_EVIDENCE_USER_TEMPLATE.format(
        evidence_json=json.dumps(
            evidence,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )
    )

###############################################################################
def build_response_prompt(evidence: Any) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": build_grounded_response_system_prompt(),
        },
        {
            "role": "user",
            "content": build_verified_evidence_prompt(evidence),
        },
    ]
