from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from AEGIS.app.constants import (
    GEONAMES_ADDRESS_FULL_WEIGHT,
    GEONAMES_ADDRESS_MULTI_COMPONENT_WEIGHT,
    GEONAMES_ADDRESS_SINGLE_COMPONENT_WEIGHT,
    GEONAMES_FUZZY_WEIGHT_FACTOR,
    GEONAMES_QUERY_ADDRESS_MULTI_WEIGHT,
    GEONAMES_QUERY_ADDRESS_SINGLE_WEIGHT,
    GEONAMES_QUERY_CITY_WEIGHT,
    GEONAMES_QUERY_COUNTRY_WEIGHT,
)
from AEGIS.app.configurations import Configuration
from AEGIS.app.utils.repository.database import GeonamesRecord, database


###############################################################################
class GeonameProperties:
    settings_cache: dict[str, Any] | None = None
    token_splitter = re.compile(r"[^0-9a-z]+")
    search_columns = (
        "name",
        "asciiname",
        "alternatenames",
        "admin1_code",
        "admin2_code",
        "admin3_code",
        "admin4_code",
    )

    def __init__(
        self,
        country: str | None,
        city: str | None,
        address: str | None,
    ) -> None:
        database.initialize_database()
        self.country = self.normalize_value(country)
        self.city = self.normalize_value(city)
        self.address = self.normalize_value(address)
        self.target_country_codes: set[str] = set()
        self.address_components = self.extract_address_components(self.address)
        self.queries = self.build_queries()
        settings = self.get_settings()
        self.max_results = settings["max_results"]
        self.partial_limit = settings["partial_limit"]
        self.fuzzy_threshold = settings["fuzzy_threshold"]

    # -------------------------------------------------------------------------
    def lookup(self) -> list[dict[str, Any]]:
        with database.Session() as session:
            self.target_country_codes = self.resolve_country_codes(session)
            candidates: dict[int, dict[str, Any]] = {}
            address_checked = False
            if self.address or self.address_components:
                address_checked = self.search_address(session, candidates)
                if address_checked:
                    refined_candidates = self.refine_candidates_by_location(candidates)
                    if refined_candidates:
                        return self.serialize_candidates(refined_candidates)
                    if candidates:
                        return self.serialize_candidates(candidates)
                    candidates.clear()
            if not address_checked:
                self.search_without_address(session, candidates)
            return self.serialize_candidates(candidates)

    # -------------------------------------------------------------------------
    def search_address(
        self,
        session: Session,
        candidates: dict[int, dict[str, Any]],
    ) -> bool:
        values: list[tuple[str, float]] = []
        if self.address:
            values.append((self.address, GEONAMES_ADDRESS_FULL_WEIGHT))
        for component in self.address_components:
            if any(component == value for value, _ in values):
                continue
            weight = (
                GEONAMES_ADDRESS_MULTI_COMPONENT_WEIGHT
                if " " in component
                else GEONAMES_ADDRESS_SINGLE_COMPONENT_WEIGHT
            )
            values.append((component, weight))
        if not values:
            return False
        values.sort(key=lambda item: len(item[0]), reverse=True)
        found_exact = False
        for value, weight in values:
            if len(candidates) >= self.max_results:
                return True
            if self.search_value_exact(session, value, weight, "address", candidates):
                found_exact = True
        if found_exact:
            return True
        found_partial = False
        for value, weight in values:
            if len(candidates) >= self.max_results:
                return True
            if self.search_value_partial(session, value, weight, "address", candidates):
                found_partial = True
        if found_partial:
            return True
        fuzzy_found = False
        for value, weight in values:
            if len(candidates) >= self.max_results:
                break
            if self.search_value_fuzzy(session, value, weight, "address", candidates):
                fuzzy_found = True
        return fuzzy_found

    # -------------------------------------------------------------------------
    def search_without_address(
        self,
        session: Session,
        candidates: dict[int, dict[str, Any]],
    ) -> None:
        if not self.queries:
            return
        for context in ("city", "country"):
            for query in self.queries:
                if query["context"] != context:
                    continue
                self.match_query(session, query, candidates)
                if len(candidates) >= self.max_results:
                    return

    # -------------------------------------------------------------------------
    def get_search_columns(self, context: str) -> tuple[str, ...]:
        if context == "country":
            return ("name", "asciiname", "alternatenames", "country_code")
        return self.search_columns

    # -------------------------------------------------------------------------
    def search_value_exact(
        self,
        session: Session,
        value: str,
        weight: float,
        context: str,
        candidates: dict[int, dict[str, Any]],
    ) -> bool:
        matched = False
        for column_name in self.get_search_columns(context):
            column = getattr(GeonamesRecord, column_name)
            stmt = (
                select(GeonamesRecord)
                .where(func.lower(column) == value)
                .order_by(GeonamesRecord.population.desc().nullslast())
                .limit(self.max_results)
            )
            for record in session.execute(stmt).scalars():
                self.store_candidate(
                    candidates,
                    record,
                    1.0 * weight,
                    "exact",
                    column_name,
                    context,
                    value,
                )
                matched = True
                if len(candidates) >= self.max_results:
                    return True
        return matched

    # -------------------------------------------------------------------------
    def search_value_partial(
        self,
        session: Session,
        value: str,
        weight: float,
        context: str,
        candidates: dict[int, dict[str, Any]],
    ) -> bool:
        matched = False
        pattern = f"%{value}%"
        for column_name in self.get_search_columns(context):
            column = getattr(GeonamesRecord, column_name)
            stmt = (
                select(GeonamesRecord)
                .where(func.lower(column).like(pattern))
                .order_by(GeonamesRecord.population.desc().nullslast())
                .limit(self.partial_limit)
            )
            for record in session.execute(stmt).scalars():
                score, match_type = self.evaluate_record(record, column_name, value)
                if score <= 0.0:
                    continue
                self.store_candidate(
                    candidates,
                    record,
                    score * weight,
                    match_type,
                    column_name,
                    context,
                    value,
                )
                matched = True
                if len(candidates) >= self.max_results:
                    return True
        return matched

    # -------------------------------------------------------------------------
    def search_value_fuzzy(
        self,
        session: Session,
        value: str,
        weight: float,
        context: str,
        candidates: dict[int, dict[str, Any]],
    ) -> bool:
        tokens = self.tokenize_value(value)
        if not tokens:
            return False
        matched = False
        for token in tokens:
            pattern = f"%{token}%"
            for column_name in self.get_search_columns(context):
                column = getattr(GeonamesRecord, column_name)
                stmt = (
                    select(GeonamesRecord)
                    .where(func.lower(column).like(pattern))
                    .order_by(GeonamesRecord.population.desc().nullslast())
                    .limit(self.partial_limit)
                )
                for record in session.execute(stmt).scalars():
                    base_score, base_type = self.evaluate_record(record, column_name, value)
                    token_score, token_type = self.evaluate_record(record, column_name, token)
                    if token_score > base_score:
                        base_score = token_score
                        base_type = token_type
                    if base_score <= 0.0:
                        continue
                    self.store_candidate(
                        candidates,
                        record,
                        base_score * (weight * GEONAMES_FUZZY_WEIGHT_FACTOR),
                        base_type or "fuzzy",
                        column_name,
                        context,
                        value,
                    )
                    matched = True
                    if len(candidates) >= self.max_results:
                        return True
        return matched

    # -------------------------------------------------------------------------
    def refine_candidates_by_location(
        self,
        candidates: dict[int, dict[str, Any]],
    ) -> dict[int, dict[str, Any]]:
        if not candidates:
            return {}
        refined: dict[int, dict[str, Any]] = candidates
        if self.target_country_codes:
            filtered: dict[int, dict[str, Any]] = {}
            for key, item in refined.items():
                record: GeonamesRecord = item["record"]
                country_code = cast(str | None, record.country_code)
                if country_code and country_code in self.target_country_codes:
                    filtered[key] = item
            if filtered:
                refined = filtered
        if self.city:
            city_filtered: dict[int, dict[str, Any]] = {}
            for key, item in refined.items():
                record = item["record"]
                if self.record_matches_city(record):
                    city_filtered[key] = item
            if city_filtered:
                refined = city_filtered
        return refined

    # -------------------------------------------------------------------------
    def record_matches_city(self, record: GeonamesRecord) -> bool:
        if not self.city:
            return False
        for column_name in self.get_search_columns("city"):
            score, _ = self.evaluate_record(record, column_name, self.city)
            if score > 0.0:
                return True
        return False

    # -------------------------------------------------------------------------
    def match_query(
        self,
        session: Session,
        query: dict[str, Any],
        candidates: dict[int, dict[str, Any]],
    ) -> None:
        value = query["value"]
        if not value:
            return
        weight = query["weight"]
        context = query["context"]
        for column_name in self.get_search_columns(context):
            column = getattr(GeonamesRecord, column_name)
            stmt = (
                select(GeonamesRecord)
                .where(func.lower(column) == value)
                .order_by(GeonamesRecord.population.desc().nullslast())
                .limit(self.max_results)
            )
            for record in session.execute(stmt).scalars():
                self.store_candidate(
                    candidates,
                    record,
                    1.0 * weight,
                    "exact",
                    column_name,
                    context,
                    value,
                )
            if len(candidates) >= self.max_results:
                return

        partial_value = f"%{value}%"
        for column_name in self.get_search_columns(context):
            column = getattr(GeonamesRecord, column_name)
            stmt = (
                select(GeonamesRecord)
                .where(func.lower(column).like(partial_value))
                .order_by(GeonamesRecord.population.desc().nullslast())
                .limit(self.partial_limit)
            )
            for record in session.execute(stmt).scalars():
                score, match_type = self.evaluate_record(record, column_name, value)
                if score <= 0.0:
                    continue
                self.store_candidate(
                    candidates,
                    record,
                    score * weight,
                    match_type,
                    column_name,
                    context,
                    value,
                )
                if len(candidates) >= self.max_results:
                    return

    # -------------------------------------------------------------------------
    def resolve_country_codes(self, session: Session) -> set[str]:
        if not self.country:
            return set()
        codes: set[str] = set()
        value = self.country
        base_filters = (GeonamesRecord.feature_class == "A",)
        for column_name in ("name", "asciiname"):
            column = getattr(GeonamesRecord, column_name)
            stmt = (
                select(GeonamesRecord.country_code)
                .where(func.lower(column) == value, *base_filters)
                .limit(10)
            )
            codes.update(
                code for code in session.execute(stmt).scalars() if code
            )
        if codes:
            return codes
        pattern = f"%{value}%"
        for column_name in ("name", "asciiname", "alternatenames"):
            column = getattr(GeonamesRecord, column_name)
            stmt = (
                select(GeonamesRecord.country_code)
                .where(func.lower(column).like(pattern), *base_filters)
                .limit(25)
            )
            codes.update(
                code for code in session.execute(stmt).scalars() if code
            )
        if codes:
            return codes
        tokens = self.tokenize_value(value)
        for token in tokens:
            pattern = f"%{token}%"
            for column_name in ("name", "asciiname", "alternatenames"):
                column = getattr(GeonamesRecord, column_name)
                stmt = (
                    select(GeonamesRecord.country_code)
                    .where(func.lower(column).like(pattern), *base_filters)
                    .limit(25)
                )
                codes.update(
                    code for code in session.execute(stmt).scalars() if code
                )
            if codes:
                break
        return codes

    # -------------------------------------------------------------------------
    def compute_country_boost(self, record: GeonamesRecord) -> float:
        if not self.target_country_codes:
            return 0.0
        if record.country_code and record.country_code in self.target_country_codes:
            return 0.1
        return 0.0

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
                    "base_score": round(item["raw_score"], 4),
                    "country_match": item["country_match"],
                    "matched_column": item["column"],
                    "matched_context": item["context"],
                    "matched_value": item["value"],
                    "feature_class": record.feature_class,
                    "feature_code": record.feature_code,
                    "population": record.population,
                    "admin1_code": record.admin1_code,
                    "admin2_code": record.admin2_code,
                    "admin3_code": record.admin3_code,
                    "admin4_code": record.admin4_code,
                    "timezone": record.timezone,
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
        context: str,
        value: str,
    ) -> None:
        if score <= 0.0 or not match_type:
            return
        boost = self.compute_country_boost(record)
        total_score = score + boost
        existing = candidates.get(record.geonameid)
        if existing and existing["score"] >= total_score:
            return
        candidates[record.geonameid] = {
            "record": record,
            "score": total_score,
            "raw_score": score,
            "country_match": bool(boost),
            "match_type": match_type,
            "column": column,
            "context": context,
            "value": value,
        }

    # -------------------------------------------------------------------------
    def evaluate_record(
        self,
        record: GeonamesRecord,
        column: str,
        query_value: str,
    ) -> tuple[float, str]:
        values = self.extract_column_values(record, column)
        best_score = 0.0
        best_type = ""
        for value in values:
            score, match_type = self.evaluate_value(value, query_value)
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
    def evaluate_value(self, value: str, query_value: str) -> tuple[float, str]:
        if not query_value or not value:
            return 0.0, ""
        if value == query_value:
            return 1.0, "exact"
        if query_value in value or value in query_value:
            ratio = SequenceMatcher(None, query_value, value).ratio()
            return ratio, "partial"
        ratio = SequenceMatcher(None, query_value, value).ratio()
        if ratio >= self.fuzzy_threshold:
            return ratio, "fuzzy"
        return 0.0, ""

    # -------------------------------------------------------------------------
    def normalize_value(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = unicodedata.normalize("NFKD", value)
        ascii_normalized = "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        )
        stripped = ascii_normalized.strip().lower()
        return stripped or None

    # -------------------------------------------------------------------------
    def extract_address_components(self, address: str | None) -> list[str]:
        if not address:
            return []
        components: list[str] = []
        tokens = self.tokenize_value(address)
        components.extend(tokens)
        for index in range(len(tokens) - 1):
            combined = f"{tokens[index]} {tokens[index + 1]}"
            if combined not in components:
                components.append(combined)
        normalized_address = self.normalize_value(address)
        if (
            normalized_address
            and normalized_address not in components
            and len(normalized_address) >= 3
        ):
            components.append(normalized_address)
        unique_components: list[str] = []
        for value in components:
            if value not in unique_components:
                unique_components.append(value)
        return unique_components

    # -------------------------------------------------------------------------
    def build_queries(self) -> list[dict[str, Any]]:
        queries: list[dict[str, Any]] = []
        if self.city:
            queries.append(
                {
                    "context": "city",
                    "value": self.city,
                    "weight": GEONAMES_QUERY_CITY_WEIGHT,
                }
            )
        for component in self.address_components:
            weight = (
                GEONAMES_QUERY_ADDRESS_MULTI_WEIGHT
                if " " in component
                else GEONAMES_QUERY_ADDRESS_SINGLE_WEIGHT
            )
            queries.append(
                {
                    "context": "address",
                    "value": component,
                    "weight": weight,
                }
            )
        if self.country:
            queries.append(
                {
                    "context": "country",
                    "value": self.country,
                    "weight": GEONAMES_QUERY_COUNTRY_WEIGHT,
                }
            )
        seen: set[str] = set()
        unique_queries: list[dict[str, Any]] = []
        for query in queries:
            key = f"{query['context']}::{query['value']}"
            if key in seen:
                continue
            seen.add(key)
            unique_queries.append(query)
        return unique_queries

    # -------------------------------------------------------------------------
    def tokenize_value(self, value: str) -> list[str]:
        if not value:
            return []
        normalized = self.normalize_value(value)
        if not normalized:
            return []
        tokens = [
            token
            for token in self.token_splitter.split(normalized)
            if token and len(token) >= 3
        ]
        unique_tokens: list[str] = []
        for token in tokens:
            if token not in unique_tokens:
                unique_tokens.append(token)
        return unique_tokens

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
