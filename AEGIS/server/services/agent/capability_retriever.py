from __future__ import annotations

import re
import unicodedata
from typing import Any

from AEGIS.server.domain.agent.decision import CapabilityCandidate
from AEGIS.server.domain.extraction.models import TurnParseResult
from AEGIS.server.services.geospatial.capability_registry import CapabilityRegistry


class CapabilityRetriever:
    def __init__(
        self,
        *,
        vector_retriever: Any | None = None,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        self.vector_retriever = vector_retriever
        self.capability_registry = capability_registry or CapabilityRegistry()

    def compose_retrieval_query(self, turn: TurnParseResult) -> str:
        parts = [turn.normalized_intent.intent_label, turn.user_text]
        if turn.temporal_signal.mode != "none":
            parts.append(turn.temporal_signal.mode)
        return " | ".join(parts)

    def _get_vector_retriever(self) -> Any | None:
        if self.vector_retriever is not None:
            return self.vector_retriever
        return None

    def _tokenize(self, value: object) -> set[str]:
        if value is None:
            return set()
        text = unicodedata.normalize("NFKC", str(value)).casefold()
        base_parts = [
            part for part in re.split(r"[^\w]+", text, flags=re.UNICODE) if part
        ]
        tokens = set(base_parts)
        for part in base_parts:
            tokens.update(chunk for chunk in part.split("_") if chunk)
        return tokens

    def _collect_tokens(self, values: object) -> set[str]:
        if values is None:
            return set()
        if isinstance(values, dict):
            tokens: set[str] = set()
            for item in values.values():
                tokens.update(self._collect_tokens(item))
            return tokens
        if isinstance(values, (list, tuple, set)):
            tokens: set[str] = set()
            for item in values:
                tokens.update(self._collect_tokens(item))
            return tokens
        return self._tokenize(values)

    def _capability_tokens(self, capability: dict[str, object]) -> set[str]:
        metadata = capability.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        return self._collect_tokens(
            [
                capability.get("id"),
                capability.get("name"),
                capability.get("description"),
                capability.get("capabilities"),
                metadata.get("keywords"),
                metadata.get("intent_tags"),
                metadata.get("task_tags"),
                metadata.get("map_type_tags"),
                metadata.get("human_summary"),
                metadata.get("primary_use_cases"),
                metadata.get("search_examples"),
            ]
        )

    def _score_capability(
        self,
        capability: dict[str, object],
        query_tokens: set[str],
    ) -> float:
        if not query_tokens:
            return 0.0
        matches = query_tokens.intersection(self._capability_tokens(capability))
        return float(len(matches)) / float(len(query_tokens))

    def _candidate_from_capability(
        self,
        capability: dict[str, object],
        *,
        kind: str,
        score: float,
    ) -> CapabilityCandidate | None:
        capability_id = str(capability.get("id") or "").strip()
        if not capability_id:
            return None
        metadata = (
            capability.get("metadata")
            if isinstance(capability.get("metadata"), dict)
            else {}
        )
        return CapabilityCandidate(
            capability_id=capability_id,
            kind=kind,  # type: ignore[arg-type]
            provider=str(
                capability.get("provider") or metadata.get("provider") or "unknown"
            ),
            score=score,
            supports_map=bool(capability.get("supports_map", kind != "tool")),
            supports_direct_text=bool(
                capability.get("supports_direct_text")
                or metadata.get("supports_direct_text")
                or capability_id
                in {
                    "location_to_coordinates",
                    "get_weather_forecast",
                    "get_air_quality_forecast",
                    "get_nearby_poi",
                    "openmeteo_weather_forecast",
                    "openmeteo_air_quality_forecast",
                    "overpass_poi_amenities",
                    "openaq_air_quality",
                    "pvgis_solar",
                }
            ),
        )

    def _retrieve_manifest_candidates(
        self, turn: TurnParseResult
    ) -> list[CapabilityCandidate]:
        query_tokens = self._collect_tokens(self.compose_retrieval_query(turn))
        candidates: list[CapabilityCandidate] = []
        for kind, items in (
            ("basemap", self.capability_registry.list_basemaps()),
            ("overlay", self.capability_registry.list_overlays()),
            ("tool", self.capability_registry.list_tools()),
        ):
            ranked: list[CapabilityCandidate] = []
            for item in items:
                score = self._score_capability(item, query_tokens)
                candidate = self._candidate_from_capability(
                    item, kind=kind, score=score
                )
                if candidate is not None:
                    ranked.append(candidate)
            ranked.sort(key=lambda item: item.score, reverse=True)
            candidates.extend(ranked[:12 if kind == "overlay" else 4])
        return candidates

    def retrieve_candidates(self, turn: TurnParseResult) -> list[CapabilityCandidate]:
        query = self.compose_retrieval_query(turn)
        retrieval = {"basemaps": [], "overlays": [], "tools": [], "providers": []}
        vector = self._get_vector_retriever()
        if vector is not None:
            retrieval = vector.retrieve_candidates(
                query, top_k=12, basemap_k=3, overlay_k=9
            )
        else:
            return self._retrieve_manifest_candidates(turn)

        candidates: list[CapabilityCandidate] = []
        for kind, item_kind in (("basemaps", "basemap"), ("overlays", "overlay")):
            for item in retrieval.get(kind, []):
                if not isinstance(item, dict):
                    continue
                metadata = (
                    item.get("metadata")
                    if isinstance(item.get("metadata"), dict)
                    else {}
                )
                candidates.append(
                    CapabilityCandidate(
                        capability_id=str(item.get("id")),
                        kind=item_kind,
                        provider=str(metadata.get("provider") or "unknown"),
                        score=float(item.get("score") or 0.0),
                        supports_map=True,
                        supports_direct_text=bool(
                            str(item.get("id") or "")
                            in {
                                "openmeteo_weather_forecast",
                                "openmeteo_air_quality_forecast",
                                "overpass_poi_amenities",
                                "openaq_air_quality",
                                "pvgis_solar",
                            }
                        ),
                    )
                )
        for item in retrieval.get("tools", []):
            if not isinstance(item, dict):
                continue
            metadata = (
                item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            )
            candidates.append(
                CapabilityCandidate(
                    capability_id=str(item.get("id")),
                    kind="tool",
                    provider=str(metadata.get("provider") or "unknown"),
                    score=float(item.get("score") or 0.0),
                    supports_map=bool(metadata.get("runtime_supports_map", False)),
                    supports_direct_text=bool(
                        metadata.get("runtime_supports_direct_text", True)
                    ),
                )
            )
        return candidates
