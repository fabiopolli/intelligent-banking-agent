from __future__ import annotations

import json
from pathlib import Path

from app.services.knowledge.schemas import KnowledgeDocument


CURATED_CATALOG_PATH = Path("knowledge/catalog/products.json")


class CuratedCatalogLoader:
    def __init__(self, catalog_path: Path = CURATED_CATALOG_PATH) -> None:
        self._catalog_path = catalog_path

    def load_documents(self) -> list[KnowledgeDocument]:
        payload = json.loads(self._catalog_path.read_text(encoding="utf-8"))
        documents = [KnowledgeDocument(**item) for item in payload["documents"]]
        self._validate(documents)
        return [document for document in documents if document.status == "published"]

    def _validate(self, documents: list[KnowledgeDocument]) -> None:
        identifiers = [document.knowledge_id for document in documents]
        if not identifiers or any(not identifier for identifier in identifiers):
            raise ValueError("Every curated knowledge document requires a knowledge_id.")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Curated knowledge_id values must be unique.")
        for document in documents:
            if not document.source or not document.text or not document.reviewed_at:
                raise ValueError(f"Curated document {document.knowledge_id} is incomplete.")
