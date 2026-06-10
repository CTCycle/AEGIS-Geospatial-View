from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from server.domain.geospatial.search import IndexedFeature, SearchIndex


###############################################################################
def build_feature_search_index(features: list[IndexedFeature]) -> SearchIndex:
    terms: dict[str, list[str]] = {}
    for feature in features:
        for term in _terms_for_feature(feature):
            terms.setdefault(term, []).append(feature.id)
    return SearchIndex(features=features, terms=terms)


###############################################################################
def deduplicate_features(features: list[IndexedFeature]) -> list[IndexedFeature]:
    deduped: list[IndexedFeature] = []
    seen: set[tuple[object, ...]] = set()
    for feature in features:
        key = (
            round(feature.latitude, 6) if feature.latitude is not None else None,
            round(feature.longitude, 6) if feature.longitude is not None else None,
            feature.label.strip().casefold(),
            (feature.category or "").strip().casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(feature)
    return deduped


###############################################################################
def build_geojson_search_index(path: str | Path) -> SearchIndex:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    indexed: list[IndexedFeature] = []
    for index, feature in enumerate(payload.get("features", [])):
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
        coordinates = _point_coordinates(feature.get("geometry"))
        indexed.append(
            IndexedFeature(
                id=str(feature.get("id") or properties.get("id") or index),
                label=str(properties.get("name") or properties.get("label") or properties.get("title") or ""),
                category=str(properties.get("category") or "") or None,
                source=str(properties.get("source") or "") or None,
                longitude=coordinates[0] if coordinates else None,
                latitude=coordinates[1] if coordinates else None,
                metadata=dict(properties),
            )
        )
    return build_feature_search_index(indexed)


###############################################################################
def query_search_index(index: SearchIndex, query: str, *, limit: int = 20) -> list[IndexedFeature]:
    wanted = {term for term in _tokenize(query) if term}
    if not wanted:
        return []
    score_by_id: dict[str, int] = {}
    for term in wanted:
        for feature_id in index.terms.get(term, []):
            score_by_id[feature_id] = score_by_id.get(feature_id, 0) + 1
    feature_by_id = {feature.id: feature for feature in index.features}
    ranked_ids = sorted(score_by_id, key=lambda item: (-score_by_id[item], item))
    return [feature_by_id[feature_id] for feature_id in ranked_ids[:limit] if feature_id in feature_by_id]


###############################################################################
def _terms_for_feature(feature: IndexedFeature) -> set[str]:
    values = [feature.label, feature.category or "", feature.source or ""]
    values.extend(str(value) for value in feature.metadata.values() if isinstance(value, str))
    terms: set[str] = set()
    for value in values:
        terms.update(_tokenize(value))
    return terms


###############################################################################
def _tokenize(value: str) -> list[str]:
    cleaned = "".join(char.lower() if char.isalnum() else " " for char in value)
    return [term for term in cleaned.split() if len(term) >= 2]


###############################################################################
def _point_coordinates(geometry: Any) -> tuple[float, float] | None:
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        return None
    coordinates = geometry.get("coordinates")
    if (
        isinstance(coordinates, list)
        and len(coordinates) >= 2
        and isinstance(coordinates[0], int | float)
        and isinstance(coordinates[1], int | float)
    ):
        return float(coordinates[0]), float(coordinates[1])
    return None
