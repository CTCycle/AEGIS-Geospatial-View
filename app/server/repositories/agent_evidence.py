"""Repository boundary for compressed agent evidence payloads."""

from __future__ import annotations

import hashlib
import json
import zlib

from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import select

from server.domain.agent.evidence import AgentEvidenceSummary, EvidenceStatus
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.schemas.models import AgentEvidenceRecord, ConversationRecord


class AgentEvidenceRepository:
    """Store bounded evidence and expose only verified payloads to services."""

    MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
    MAX_SUMMARY_BYTES = 32 * 1024
    MAX_PARENTS = 32

    def __init__(self, database: SQLiteRepository) -> None:
        self._session_factory = database.session

    def create(
        self,
        *,
        conversation_id: str,
        run_id: str | None,
        kind: str,
        media_type: str,
        status: EvidenceStatus,
        payload: Any,
        summary: dict[str, Any] | None = None,
        provenance: dict[str, Any] | None = None,
        parent_evidence_ids: list[str] | None = None,
    ) -> AgentEvidenceSummary:
        raw = (
            payload
            if isinstance(payload, bytes)
            else self._json_bytes(self._sanitize_payload(payload))
        )
        if len(raw) > self.MAX_PAYLOAD_BYTES:
            raise ValueError("Evidence payload exceeds the provider-size ceiling.")
        bounded_summary = self._sanitize_object(summary or {})
        bounded_provenance = self._sanitize_object(provenance or {})
        if len(self._json_bytes(bounded_summary)) > self.MAX_SUMMARY_BYTES:
            raise ValueError("Evidence summary exceeds the bounded summary limit.")
        parents = [str(value) for value in (parent_evidence_ids or [])[: self.MAX_PARENTS]]
        evidence_id = f"evidence_{uuid4().hex}"
        digest = hashlib.sha256(raw).hexdigest()
        record = AgentEvidenceRecord(
            id=evidence_id,
            conversation_id=conversation_id,
            run_id=run_id,
            kind=kind,
            media_type=media_type,
            status=status,
            summary_json=bounded_summary,
            provenance_json=bounded_provenance,
            payload_blob=zlib.compress(raw, level=6),
            uncompressed_byte_size=len(raw),
            sha256=digest,
            parent_evidence_ids=parents,
            created_at=datetime.now(UTC),
        )
        with self._session_factory() as session:
            if session.get(ConversationRecord, conversation_id) is None:
                raise ValueError("Conversation not found.")
            if parents:
                owned_parent_ids = set(
                    session.scalars(
                        select(AgentEvidenceRecord.id).where(
                            AgentEvidenceRecord.conversation_id == conversation_id,
                            AgentEvidenceRecord.id.in_(parents),
                        )
                    ).all()
                )
                if owned_parent_ids != set(parents):
                    raise ValueError(
                        "Parent evidence references must belong to the conversation."
                    )
            session.add(record)
            session.commit()
        return self._summary(record)

    def get_summary(
        self,
        evidence_id: str,
        *,
        conversation_id: str | None = None,
    ) -> AgentEvidenceSummary | None:
        with self._session_factory() as session:
            record = session.get(AgentEvidenceRecord, evidence_id)
            if (
                record is not None
                and conversation_id is not None
                and record.conversation_id != conversation_id
            ):
                record = None
            return self._summary(record) if record is not None else None

    def get_payload(
        self,
        evidence_id: str,
        *,
        conversation_id: str | None = None,
    ) -> tuple[AgentEvidenceSummary, bytes] | None:
        with self._session_factory() as session:
            record = session.get(AgentEvidenceRecord, evidence_id)
            if record is None or (
                conversation_id is not None
                and record.conversation_id != conversation_id
            ):
                return None
            raw = zlib.decompress(record.payload_blob)
            if len(raw) != record.uncompressed_byte_size:
                raise ValueError("Evidence payload size verification failed.")
            if hashlib.sha256(raw).hexdigest() != record.sha256:
                raise ValueError("Evidence payload checksum verification failed.")
            return self._summary(record), raw

    def list_summaries(self, conversation_id: str, *, limit: int = 100) -> list[AgentEvidenceSummary]:
        bounded_limit = max(1, min(int(limit), 500))
        with self._session_factory() as session:
            records = session.scalars(
                select(AgentEvidenceRecord)
                .where(AgentEvidenceRecord.conversation_id == conversation_id)
                .order_by(AgentEvidenceRecord.created_at.desc())
                .limit(bounded_limit)
            ).all()
            return [self._summary(record) for record in records]

    @staticmethod
    def _json_bytes(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

    @classmethod
    def _sanitize_payload(cls, value: Any, *, depth: int = 0) -> Any:
        """Remove credential-shaped fields without truncating data records."""

        if depth > 16:
            return "[depth-limited]"
        secret_keys = {
            "authorization",
            "cookie",
            "set-cookie",
            "api_key",
            "apikey",
            "token",
            "password",
            "secret",
        }
        if isinstance(value, dict):
            mapping = cast(dict[Any, Any], value)
            return {
                str(key): cls._sanitize_payload(child, depth=depth + 1)
                for key, child in mapping.items()
                if not cls._is_secret_key(str(key), secret_keys)
            }
        if isinstance(value, list):
            items = cast(list[Any], value)
            return [cls._sanitize_payload(child, depth=depth + 1) for child in items]
        if isinstance(value, tuple):
            items = cast(tuple[Any, ...], value)
            return [cls._sanitize_payload(child, depth=depth + 1) for child in items]
        return value

    @classmethod
    def _sanitize_object(cls, value: Any, *, depth: int = 0) -> Any:
        if depth > 8:
            return "[depth-limited]"
        secret_keys = {"authorization", "cookie", "set-cookie", "api_key", "apikey", "token", "password", "secret"}
        if isinstance(value, dict):
            mapping = cast(dict[Any, Any], value)
            return {
                str(key): cls._sanitize_object(child, depth=depth + 1)
                for key, child in mapping.items()
                if not cls._is_secret_key(str(key), secret_keys)
            }
        if isinstance(value, list):
            items = cast(list[Any], value)
            return [cls._sanitize_object(child, depth=depth + 1) for child in items[:1000]]
        if isinstance(value, str):
            return value[:4096]
        return value

    @staticmethod
    def _is_secret_key(key: str, secret_keys: set[str]) -> bool:
        normalized = key.casefold().replace("-", "_")
        return normalized in secret_keys or any(
            marker in normalized
            for marker in ("authorization", "access_token", "api_key", "password", "secret", "cookie")
        ) or normalized.endswith("_token")

    @staticmethod
    def _summary(record: AgentEvidenceRecord) -> AgentEvidenceSummary:
        raw_summary = record.summary_json or {}
        raw_provenance = record.provenance_json or {}
        map_eligibility = str(raw_summary.get("map_eligibility") or "unknown")
        if map_eligibility not in {"renderable", "not_renderable", "unknown"}:
            map_eligibility = "unknown"
        return AgentEvidenceSummary(
            evidence_id=record.id,
            kind=record.kind,  # type: ignore[arg-type]
            media_type=record.media_type,
            status=record.status,  # type: ignore[arg-type]
            summary=raw_summary,
            provenance=raw_provenance,
            parent_evidence_ids=[str(item) for item in (record.parent_evidence_ids or [])],
            byte_size=record.uncompressed_byte_size,
            sha256=record.sha256,
            map_eligibility=map_eligibility,  # type: ignore[arg-type]
        )
