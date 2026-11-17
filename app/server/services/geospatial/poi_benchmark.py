from __future__ import annotations

from server.common.typing import is_json_array, is_json_object, json_object

import argparse
import json
from dataclasses import dataclass
from math import hypot
from pathlib import Path
from typing import Any


###############################################################################
@dataclass(frozen=True)
class POIParityThresholds:
    min_recall: float = 0.80
    min_precision: float = 0.80
    min_name_completeness: float = 0.90
    min_coordinate_completeness: float = 1.0
    max_duplicate_rate: float = 0.10


###############################################################################
@dataclass(frozen=True)
class POIParityReport:
    baseline_count: int
    candidate_count: int
    matched_count: int
    recall: float
    precision: float
    name_completeness: float
    coordinate_completeness: float
    duplicate_rate: float
    meets_thresholds: bool


###############################################################################
def load_poi_records(path: str | Path) -> list[dict[str, Any]]:
    """Load normalized POI records from a provider payload or GeoJSON file."""
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if is_json_object(payload) and is_json_object(payload.get("payload")):
        payload = payload["payload"]
    if is_json_object(payload) and is_json_array(payload.get("features")):
        raw_features = payload["features"]
    elif is_json_array(payload):
        raw_features = payload
    else:
        raise ValueError(
            f"{source} must contain a POI list or FeatureCollection payload."
        )

    records: list[dict[str, Any]] = []
    for raw in raw_features:
        if not is_json_object(raw):
            continue
        if (
            _number(raw.get("latitude")) is not None
            and _number(raw.get("longitude")) is not None
        ):
            records.append(dict(raw))
            continue
        properties = json_object(raw.get("properties"))
        geometry = json_object(raw.get("geometry"))
        coordinates = geometry.get("coordinates")
        if not is_json_array(coordinates) or len(coordinates) < 2:
            continue
        records.append(
            {
                "id": raw.get("id") or properties.get("id"),
                "name": properties.get("name"),
                "category": properties.get("category") or properties.get("kinds"),
                "latitude": coordinates[1],
                "longitude": coordinates[0],
            }
        )
    return records


###############################################################################
def benchmark_poi_parity(
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    *,
    thresholds: POIParityThresholds | None = None,
) -> POIParityReport:
    thresholds = thresholds or POIParityThresholds()
    matches = sum(1 for item in baseline if _find_match(item, candidate))
    baseline_count = len(baseline)
    candidate_count = len(candidate)
    recall = matches / baseline_count if baseline_count else 1.0
    precision = (
        matches / candidate_count if candidate_count else 0.0 if baseline_count else 1.0
    )
    name_completeness = _completeness(candidate, "name")
    coordinate_completeness = (
        sum(
            1
            for item in candidate
            if _number(item.get("latitude")) is not None
            and _number(item.get("longitude")) is not None
        )
        / candidate_count
        if candidate_count
        else 1.0
    )
    duplicate_rate = (
        1.0 - (len(_dedupe_keys(candidate)) / candidate_count)
        if candidate_count
        else 0.0
    )
    passed = (
        recall >= thresholds.min_recall
        and precision >= thresholds.min_precision
        and name_completeness >= thresholds.min_name_completeness
        and coordinate_completeness >= thresholds.min_coordinate_completeness
        and duplicate_rate <= thresholds.max_duplicate_rate
    )
    return POIParityReport(
        baseline_count=baseline_count,
        candidate_count=candidate_count,
        matched_count=matches,
        recall=round(recall, 4),
        precision=round(precision, 4),
        name_completeness=round(name_completeness, 4),
        coordinate_completeness=round(coordinate_completeness, 4),
        duplicate_rate=round(duplicate_rate, 4),
        meets_thresholds=passed,
    )


###############################################################################
def _find_match(item: dict[str, Any], candidates: list[dict[str, Any]]) -> bool:
    item_id = str(item.get("id") or "").strip()
    item_name = str(item.get("name") or "").strip().casefold()
    item_lat, item_lon = _number(item.get("latitude")), _number(item.get("longitude"))
    for candidate in candidates:
        candidate_id = str(candidate.get("id") or "").strip()
        if item_id and candidate_id and item_id == candidate_id:
            return True
        if not item_name or item_lat is None or item_lon is None:
            continue
        candidate_name = str(candidate.get("name") or "").strip().casefold()
        candidate_lat, candidate_lon = (
            _number(candidate.get("latitude")),
            _number(candidate.get("longitude")),
        )
        if (
            candidate_name == item_name
            and candidate_lat is not None
            and candidate_lon is not None
            and hypot(candidate_lat - item_lat, candidate_lon - item_lon) <= 0.001
        ):
            return True
    return False


###############################################################################
def _completeness(items: list[dict[str, Any]], field: str) -> float:
    return (
        sum(1 for item in items if str(item.get(field) or "").strip()) / len(items)
        if items
        else 1.0
    )


###############################################################################
def _dedupe_keys(
    items: list[dict[str, Any]],
) -> set[tuple[str, float | None, float | None]]:
    return {
        (
            str(item.get("name") or "").strip().casefold(),
            _number(item.get("latitude")),
            _number(item.get("longitude")),
        )
        for item in items
    }


###############################################################################
def _number(value: object) -> float | None:
    try:
        return float(str(value)) if value is not None else None
    except TypeError, ValueError:
        return None


###############################################################################
def _main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark canonical POI parity.")
    parser.add_argument(
        "--baseline", required=True, help="Provider payload or GeoJSON baseline."
    )
    parser.add_argument(
        "--candidate", required=True, help="Provider payload or GeoJSON candidate."
    )
    parser.add_argument("--output", help="Optional JSON report output path.")
    args = parser.parse_args()

    report = benchmark_poi_parity(
        load_poi_records(args.baseline),
        load_poi_records(args.candidate),
    )
    result = {
        "baseline": args.baseline,
        "candidate": args.candidate,
        "report": report.__dict__,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.meets_thresholds else 2


###############################################################################
if __name__ == "__main__":
    raise SystemExit(_main())
