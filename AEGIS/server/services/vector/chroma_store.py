from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from AEGIS.server.utils.constants import PROJECT_DIR


@dataclass(frozen=True)
class VectorDocument:
    id: str
    text: str
    metadata: dict[str, Any]


class ChromaVectorStore:
    def __init__(self, persist_path: str | None = None, collection_name: str = "aegis_layers") -> None:
        self.persist_path = persist_path or os.path.join(PROJECT_DIR, "resources", "vectors")
        self.collection_name = collection_name
        os.makedirs(self.persist_path, exist_ok=True)
        self._memory_docs: list[VectorDocument] = []
        self._client = None
        self._collection = None
        try:
            import chromadb
            from chromadb.config import Settings

            self._client = chromadb.PersistentClient(
                path=self.persist_path,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = self._client.get_or_create_collection(name=self.collection_name)
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
            self._collection = self._client.get_or_create_collection(name=self.collection_name)

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
            metadatas = [item.metadata for item in documents]
            self._collection.add(ids=ids, documents=texts, metadatas=metadatas)
            return
        self._memory_docs.extend(documents)

    def similarity_search(self, query_text: str, *, top_k: int = 5) -> list[dict[str, Any]]:
        if self._collection is not None:
            result = self._collection.query(query_texts=[query_text], n_results=max(1, top_k))
            docs = result.get("documents", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            return [
                {"text": doc, "metadata": metadata or {}}
                for doc, metadata in zip(docs, metadatas, strict=False)
            ]
        tokens = {token.lower() for token in query_text.split() if token.strip()}
        scored: list[tuple[int, VectorDocument]] = []
        for document in self._memory_docs:
            corpus = document.text.lower()
            score = sum(1 for token in tokens if token in corpus)
            scored.append((score, document))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {"text": item.text, "metadata": item.metadata}
            for score, item in scored[:top_k]
            if score > 0
        ]
