from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from AEGIS.app.configurations import Configuration
from AEGIS.app.utils.repository.database import GeonamesRecord, database


###############################################################################
class GeonameProperties:
    settings_cache: dict[str, Any] | None = None

    def __init__(
        self,
        country: str | None,
        city: str | None,
        address: str | None,
    ) -> None:
        self.country = self.normalize_value(country)
        self.city = self.normalize_value(city)
        self.address = self.normalize_value(address)
        settings = self.get_settings()
        self.max_results = settings["max_results"]
        self.partial_limit = settings["partial_limit"]
        self.fuzzy_threshold = settings["fuzzy_threshold"]

    # -------------------------------------------------------------------------
    def lookup(self) -> list[dict[str, Any]]:
        if not self.country:
            return []
        with database.Session() as session:
            return self.match_country(session)

    # -------------------------------------------------------------------------
    def match_country(self, session: Session) -> list[dict[str, Any]]:
        candidates: dict[int, dict[str, Any]] = {}
        for column_name in ("name", "asciiname", "alternatenames"):
            column = getattr(GeonamesRecord, column_name)
            stmt = (
                select(GeonamesRecord)
                .where(func.lower(column) == self.country)
                .order_by(GeonamesRecord.population.desc().nullslast())
                .limit(self.max_results)
            )
            for record in session.execute(stmt).scalars():
                self.store_candidate(
                    candidates,
                    record,
                    1.0,
                    "exact",
                    column_name,
                )
            if len(candidates) >= self.max_results:
                break

        if len(candidates) >= self.max_results:
            return self.serialize_candidates(candidates)

        partial_value = f"%{self.country}%"
        for column_name in ("name", "asciiname", "alternatenames"):
            column = getattr(GeonamesRecord, column_name)
            stmt = (
                select(GeonamesRecord)
                .where(func.lower(column).like(partial_value))
                .order_by(GeonamesRecord.population.desc().nullslast())
                .limit(self.partial_limit)
            )
            for record in session.execute(stmt).scalars():
                score, match_type = self.evaluate_record(record, column_name)
                self.store_candidate(
                    candidates,
                    record,
                    score,
                    match_type,
                    column_name,
                )

        return self.serialize_candidates(candidates)

    # -------------------------------------------------------------------------
    def serialize_candidates(self, candidates: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        ordered = sorted(
            candidates.values(),
            key=lambda item: (
                item["score"],
                (item["record"].population or 0),
            ),
            reverse=True,
        )
        results: list[dict[str, Any]] = []
        for item in ordered[: self.max_results]:
            record: GeonamesRecord = item["record"]
            results.append(
                {
                    "geonameid": record.geonameid,
                    "name": record.name,
                    "asciiname": record.asciiname,
                    "country_code": record.country_code,
                    "latitude": record.latitude,
                    "longitude": record.longitude,
                    "match_type": item["match_type"],
                    "match_score": round(item["score"], 4),
                    "matched_column": item["column"],
                }
            )
        return results

    # -------------------------------------------------------------------------
    def store_candidate(
        self,
        candidates: dict[int, dict[str, Any]],
        record: GeonamesRecord,
        score: float,
        match_type: str,
        column: str,
    ) -> None:
        if score <= 0.0 or not match_type:
            return
        existing = candidates.get(record.geonameid)
        if existing and existing["score"] >= score:
            return
        candidates[record.geonameid] = {
            "record": record,
            "score": score,
            "match_type": match_type,
            "column": column,
        }

    # -------------------------------------------------------------------------
    def evaluate_record(self, record: GeonamesRecord, column: str) -> tuple[float, str]:
        values = self.extract_column_values(record, column)
        best_score = 0.0
        best_type = ""
        for value in values:
            score, match_type = self.evaluate_value(value)
            if score > best_score:
                best_score = score
                best_type = match_type
        return best_score, best_type

    # -------------------------------------------------------------------------
    def extract_column_values(self, record: GeonamesRecord, column: str) -> list[str]:
        raw_value = getattr(record, column) or ""
        if column == "alternatenames":
            return [name.strip().lower() for name in raw_value.split(",") if name]
        return [raw_value.lower()]

    # -------------------------------------------------------------------------
    def evaluate_value(self, value: str) -> tuple[float, str]:
        if not self.country or not value:
            return 0.0, ""
        if value == self.country:
            return 1.0, "exact"
        if self.country in value or value in self.country:
            ratio = SequenceMatcher(None, self.country, value).ratio()
            return ratio, "partial"
        ratio = SequenceMatcher(None, self.country, value).ratio()
        if ratio >= self.fuzzy_threshold:
            return ratio, "fuzzy"
        return 0.0, ""

    # -------------------------------------------------------------------------
    def normalize_value(self, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip().lower()
        return stripped or None

    # -------------------------------------------------------------------------
    def get_settings(self) -> dict[str, Any]:
        if GeonameProperties.settings_cache is not None:
            return GeonameProperties.settings_cache
        configuration = Configuration()
        settings = configuration.get_section("geonames")
        resolved: dict[str, Any] = {
            "max_results": 5,
            "partial_limit": 50,
            "fuzzy_threshold": 0.72,
        }
        max_results = settings.get("max_results")
        partial_limit = settings.get("partial_limit")
        fuzzy_threshold = settings.get("fuzzy_threshold")
        if isinstance(max_results, int) and max_results > 0:
            resolved["max_results"] = max_results
        if isinstance(partial_limit, int) and partial_limit > 0:
            resolved["partial_limit"] = partial_limit
        if isinstance(fuzzy_threshold, (int, float)) and 0.0 < float(fuzzy_threshold) <= 1.0:
            resolved["fuzzy_threshold"] = float(fuzzy_threshold)
        GeonameProperties.settings_cache = resolved
        return resolved
