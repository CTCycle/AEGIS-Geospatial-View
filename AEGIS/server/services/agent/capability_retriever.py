from __future__ import annotations

from typing import Any

from AEGIS.server.domain.agent.decision import CapabilityCandidate
from AEGIS.server.domain.extraction.models import TurnParseResult


class CapabilityRetriever:
    def __init__(self, *, vector_retriever: Any | None = None) -> None:
        self.vector_retriever = vector_retriever

    def compose_retrieval_query(self, turn: TurnParseResult) -> str:
        parts = [turn.normalized_intent.intent_label, turn.user_text]
        if turn.temporal_signal.mode != "none":
            parts.append(turn.temporal_signal.mode)
        return " | ".join(parts)

    def _get_vector_retriever(self) -> Any | None:
        if self.vector_retriever is not None:
            return self.vector_retriever
        try:
            from AEGIS.server.services.vector.retriever import VectorRetriever

            self.vector_retriever = VectorRetriever()
        except Exception:
            self.vector_retriever = False
        return self.vector_retriever if self.vector_retriever else None

    def retrieve_candidates(self, turn: TurnParseResult) -> list[CapabilityCandidate]:
        query = self.compose_retrieval_query(turn)
        retrieval = {"basemaps": [], "overlays": [], "tools": [], "providers": []}
        vector = self._get_vector_retriever()
        if vector is not None:
            retrieval = vector.retrieve_candidates(query, top_k=12, basemap_k=3, overlay_k=9)

        candidates: list[CapabilityCandidate] = []
        for kind, item_kind in (("basemaps", "basemap"), ("overlays", "overlay")):
            for item in retrieval.get(kind, []):
                if not isinstance(item, dict):
                    continue
                metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
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
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
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
