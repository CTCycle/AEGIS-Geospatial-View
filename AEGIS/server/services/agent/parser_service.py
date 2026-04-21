from __future__ import annotations

import re
from datetime import UTC, datetime

from AEGIS.server.domain.extraction.models import (
    ExtractedIntent,
    ExtractedIntentPatch,
    StageAParserIntent,
    StageBSearchExtraction,
)
from AEGIS.server.services.llm.factory import LLMFactory
from AEGIS.server.services.llm.prompts import (
    get_agent_enrichment_prompt,
    get_agent_extraction_prompt,
)
from AEGIS.server.services.llm.structured import (
    normalize_stage_a_payload,
    normalize_stage_b_payload,
)
from AEGIS.server.services.llm.types import ChatCompletionRequest

COORDINATE_PAIR_RE = re.compile(
    r"(?P<latitude>[+-]?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(?P<longitude>[+-]?\d{1,3}(?:\.\d+)?)"
)


def _extract_coordinate_patch(user_message: str) -> ExtractedIntentPatch:
    match = COORDINATE_PAIR_RE.search(user_message)
    if not match:
        return ExtractedIntentPatch(user_goal=user_message.strip(), certainty=0.15)

    latitude = float(match.group("latitude"))
    longitude = float(match.group("longitude"))
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return ExtractedIntentPatch(user_goal=user_message.strip(), certainty=0.15)

    return ExtractedIntentPatch(
        coordinates={"latitude": latitude, "longitude": longitude},
        user_goal=user_message.strip(),
        certainty=0.9,
    )

###############################################################################
class ParserService:
    def __init__(self, *, llm_factory: LLMFactory, provider: str, model: str) -> None:
        self.llm_factory = llm_factory
        self.provider = provider
        self.model = model

    # -------------------------------------------------------------------------
    def extract_patch(
        self,
        *,
        conversation_context: str,
        latest_state: ExtractedIntent,
        user_message: str,
    ) -> ExtractedIntentPatch:
        try:
            provider = self.llm_factory.get_parser_provider(self.provider)
            request = ChatCompletionRequest(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": get_agent_extraction_prompt(
                            provider=self.provider, model=self.model
                        ),
                    },
                    {
                        "role": "user",
                        "content": conversation_context,
                    },
                    {
                        "role": "user",
                        "content": (
                            "latest_state="
                            + str(latest_state.model_dump(mode="json"))
                            + "\nlatest_user_message="
                            + user_message
                        ),
                    },
                ],
            )
            payload = provider.structured_output(request, schema=ExtractedIntentPatch)
        except Exception:
            return _extract_coordinate_patch(user_message)
        if not isinstance(payload, dict):
            payload = {}
        return ExtractedIntentPatch.model_validate(payload)

    # -------------------------------------------------------------------------
    def _tools_summary(self, available_tools: list[dict[str, str]]) -> str:
        if not available_tools:
            return "No tools available."
        lines: list[str] = []
        for item in available_tools:
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
            if name:
                lines.append(f"- {name}: {description}")
        return "\n".join(lines) if lines else "No tools available."

    # -------------------------------------------------------------------------
    def _stage_a_fallback(
        self, user_message: str, available_tools: list[dict[str, str]]
    ) -> StageAParserIntent:
        has_coordinates = bool(COORDINATE_PAIR_RE.search(user_message))
        has_location = has_coordinates or bool(
            re.search(
                r"\b(?:near|around|in|at)\s+[a-z0-9][a-z0-9\s,'\-]{2,}",
                user_message,
                re.IGNORECASE,
            )
        )
        if not has_location and re.search(
            r"\b(?:find|show|check|locate)\s+(?:me\s+)?[A-Z][a-z]{2,}\b", user_message
        ):
            has_location = True
        if not has_location:
            tokens = re.findall(r"\b[A-Za-z]{3,}\b", user_message)
            if any(token[0].isupper() for token in tokens[1:]):
                has_location = True
        lowered = user_message.lower()
        requires_search = any(
            token in lowered
            for token in ("map", "overlay", "layer", "satellite", "traffic")
        )
        required_tools: list[str] = []
        for tool in available_tools:
            name = str(tool.get("name") or "")
            description = str(tool.get("description") or "").lower()
            if "weather" in lowered and "weather" in description:
                required_tools.append(name)
            if "air quality" in lowered and "air-quality" in description:
                required_tools.append(name)
            if "poi" in lowered and "points of interest" in description:
                required_tools.append(name)
            if any(
                token in lowered
                for token in ("coordinate", "where is", "geocode", "locate")
            ) and any(
                token in description
                for token in ("geocode", "geocoding", "latitude and longitude")
            ):
                required_tools.append(name)
        if has_coordinates:
            location_type = "coordinates"
        elif has_location:
            location_type = "address"
        else:
            location_type = None
        return StageAParserIntent(
            has_location=has_location,
            location_type=location_type,
            has_time_reference=bool(
                re.search(r"\b(today|tomorrow|yesterday|\d{4})\b", lowered)
            ),
            requires_search=requires_search,
            requires_data=requires_search,
            required_tools=list(dict.fromkeys(required_tools)),
            certainty=0.35 if has_location else 0.15,
        )

    # -------------------------------------------------------------------------
    def parse_stage_a_intent(
        self,
        *,
        conversation_context: str,
        user_message: str,
        available_tools: list[dict[str, str]],
        certainty_threshold: float,
        max_retries: int,
    ) -> StageAParserIntent:
        attempts = max(0, max_retries) + 1
        for _ in range(attempts):
            try:
                provider = self.llm_factory.get_parser_provider(self.provider)
                request = ChatCompletionRequest(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": get_agent_extraction_prompt(
                                provider=self.provider, model=self.model
                            ),
                        },
                        {"role": "user", "content": conversation_context},
                        {
                            "role": "user",
                            "content": f"latest_user_message={user_message}\navailable_tools:\n{self._tools_summary(available_tools)}",
                        },
                    ],
                )
                raw_payload = provider.structured_output(
                    request, schema=StageAParserIntent
                )
                normalized = normalize_stage_a_payload(
                    raw_payload if isinstance(raw_payload, dict) else {}
                )
                stage_a = StageAParserIntent.model_validate(normalized)
                fallback_stage = self._stage_a_fallback(user_message, available_tools)
                if fallback_stage.has_location and not stage_a.has_location:
                    stage_a = stage_a.model_copy(
                        update={
                            "has_location": True,
                            "location_type": fallback_stage.location_type,
                        }
                    )
                if fallback_stage.required_tools and not stage_a.required_tools:
                    stage_a = stage_a.model_copy(
                        update={"required_tools": fallback_stage.required_tools}
                    )
                if stage_a.certainty >= certainty_threshold:
                    return stage_a
            except Exception:
                continue
        return self._stage_a_fallback(user_message, available_tools)

    # -------------------------------------------------------------------------
    def parse_stage_b_enrichment(
        self,
        *,
        conversation_context: str,
        user_message: str,
        retrieval: dict[str, list[dict[str, object]]],
        fallback_datetime: str | None,
    ) -> StageBSearchExtraction:
        try:
            provider = self.llm_factory.get_parser_provider(self.provider)
            request = ChatCompletionRequest(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": get_agent_enrichment_prompt(
                            provider=self.provider, model=self.model
                        ),
                    },
                    {"role": "user", "content": conversation_context},
                    {
                        "role": "user",
                        "content": f"user_message={user_message}\nretrieval={retrieval}",
                    },
                ],
            )
            raw_payload = provider.structured_output(
                request, schema=StageBSearchExtraction
            )
            normalized = normalize_stage_b_payload(
                raw_payload if isinstance(raw_payload, dict) else {}
            )
            stage_b = StageBSearchExtraction.model_validate(normalized)
        except Exception:
            stage_b = StageBSearchExtraction()
        if (
            stage_b.coordinates.latitude is None
            or stage_b.coordinates.longitude is None
        ):
            match = COORDINATE_PAIR_RE.search(user_message)
            if match:
                latitude = float(match.group("latitude"))
                longitude = float(match.group("longitude"))
                if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                    payload = stage_b.model_dump(mode="json")
                    payload["coordinates"] = {
                        "latitude": latitude,
                        "longitude": longitude,
                    }
                    stage_b = StageBSearchExtraction.model_validate(payload)
        if not any(
            [stage_b.location.address, stage_b.location.city, stage_b.location.country]
        ):
            city_match = re.search(
                r"\b(?:in|at|near|around|find|show|locate)\s+(?:me\s+)?([A-Z][a-z]{2,})\b",
                user_message,
            )
            if city_match:
                payload = stage_b.model_dump(mode="json")
                payload["location"] = {
                    "address": None,
                    "city": city_match.group(1),
                    "country": None,
                    "location_type": "city",
                }
                stage_b = StageBSearchExtraction.model_validate(payload)
        if not any(
            [stage_b.location.address, stage_b.location.city, stage_b.location.country]
        ):
            city_tokens = re.findall(r"\b[A-Z][a-z]{2,}\b", user_message)
            for token in city_tokens:
                if token.lower() in {
                    "find",
                    "show",
                    "check",
                    "locate",
                    "map",
                    "give",
                    "what",
                    "where",
                    "please",
                }:
                    continue
                payload = stage_b.model_dump(mode="json")
                payload["location"] = {
                    "address": None,
                    "city": token,
                    "country": None,
                    "location_type": "city",
                }
                stage_b = StageBSearchExtraction.model_validate(payload)
                break
        if not stage_b.time_reference:
            stage_b = stage_b.model_copy(
                update={
                    "time_reference": fallback_datetime or datetime.now(UTC).isoformat()
                }
            )
        return stage_b
