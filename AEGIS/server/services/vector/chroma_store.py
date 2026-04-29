from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.config import Settings

from AEGIS.server.common.constants import PROJECT_DIR


@dataclass(frozen=True)
class VectorDocument:
    id: str
    text: str
    metadata: dict[str, Any]
    embedding: list[float] | None = None


class ChromaVectorStore:
    def __init__(
        self, persist_path: str | None = None, collection_name: str = "aegis_layers"
    ) -> None:
        self.persist_path = persist_path or os.path.join(
            PROJECT_DIR, "resources", "vectors"
        )
        self.collection_name = collection_name
        os.makedirs(self.persist_path, exist_ok=True)
        self._memory_docs: list[VectorDocument] = []
        self._client = None
        self._collection = None
        try:
            self._client = chromadb.PersistentClient(
                path=self.persist_path,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name
            )
        except Exception:
            self._client = None
            self._collection = None

    def clear(self) -> None:
        self._memory_docs = []
        if self._collection is not None:
            try:
                self._client.delete_collection(self.collection_name)
            except Exception:
                pass
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name
            )

    def exists(self) -> bool:
        if self._collection is not None:
            try:
                count = self._collection.count()
                return count > 0
            except Exception:
                return False
        return len(self._memory_docs) > 0

    def add_documents(self, documents: list[VectorDocument]) -> None:
        if not documents:
            return
        if self._collection is not None:
            ids = [item.id for item in documents]
            texts = [item.text for item in documents]
            metadatas = [_sanitize_metadata(item.metadata) for item in documents]
            if any(item.embedding for item in documents):
                embeddings = [item.embedding or [] for item in documents]
                self._collection.add(
                    ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings
                )
            else:
                self._collection.add(ids=ids, documents=texts, metadatas=metadatas)
            return
        self._memory_docs.extend(documents)

    def similarity_search(
        self, query_text: str, *, top_k: int = 5
    ) -> list[dict[str, Any]]:
        if self._collection is not None:
            result = self._collection.query(
                query_texts=[query_text], n_results=max(1, top_k)
            )
            docs = result.get("documents", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            distances = result.get("distances", [[]])[0]
            return [
                {
                    "text": doc,
                    "metadata": metadata or {},
                    "distance": distance,
                    "score": _distance_to_score(distance),
                }
                for doc, metadata, distance in zip(
                    docs, metadatas, distances, strict=False
                )
            ]
        tokens = {token.lower() for token in query_text.split() if token.strip()}
        scored: list[tuple[int, VectorDocument]] = []
        for document in self._memory_docs:
            corpus = document.text.lower()
            score = sum(1 for token in tokens if token in corpus)
            scored.append((score, document))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "text": item.text,
                "metadata": item.metadata,
                "distance": float(max(0, 100 - score)),
                "score": float(score),
            }
            for score, item in scored[:top_k]
            if score > 0
        ]


def _distance_to_score(distance: Any) -> float:
    try:
        value = float(distance)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, 1.0 - value)


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    safe: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        safe[str(key)] = _sanitize_metadata_value(value)
    return safe


def _sanitize_metadata_value(value: Any) -> str | int | float | bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return str(value)
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set, dict)):
        try:
            return json.dumps(value, ensure_ascii=True, default=str)
        except (TypeError, ValueError):
            return str(value)
    return str(value)

