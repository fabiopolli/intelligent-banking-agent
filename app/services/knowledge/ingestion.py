from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import settings
from app.services.knowledge.catalog import CuratedCatalogLoader
from app.services.knowledge.config import (
    HELP_CENTER_SOURCE,
    OFFICIAL_KNOWLEDGE_DOCUMENTS,
    POLICIES_SOURCE,
    TARIFF_PDF_PATH,
    TARIFF_PDF_SOURCE,
)
from app.services.knowledge.schemas import KnowledgeDocument
from app.services.observability import traceable


class OfficialWebSnapshotIngestor:
    @traceable(name="Official Web Snapshot Ingestion", run_type="retriever")
    def load_documents(self) -> list[KnowledgeDocument]:
        return [
            KnowledgeDocument(
                title="Central de ajuda Itau - canais de atendimento",
                source=HELP_CENTER_SOURCE,
                text=(
                    "A Central de Ajuda Itau para voce apresenta atendimento pelo WhatsApp Itau, "
                    "consulta de saldos, limites, segunda via e duvidas. Tambem destaca o chat no app "
                    "ou internet para tirar duvidas e resolver o que precisar, alem de telefones e "
                    "encontre agencias."
                ),
            ),
            KnowledgeDocument(
                title="Central de ajuda Itau - topicos frequentes",
                source=HELP_CENTER_SOURCE,
                text=(
                    "Os topicos frequentes da Central de Ajuda incluem novo app Itau, dados cadastrais, "
                    "cartao de credito, conta corrente, tarifas, boletos, pagamentos e transferencias, "
                    "acessos, iToken, seguros, renegociacao, imposto de renda e investimentos."
                ),
            ),
            KnowledgeDocument(
                title="Central de ajuda Itau - seguranca e cartao",
                source=HELP_CENTER_SOURCE,
                text=(
                    "A Central de Ajuda orienta sobre desbloqueio de cartao, senha de acesso Itau, "
                    "seguranca e fraudes, contestacao de compras no cartao de credito e uso dos canais "
                    "digitais para atendimento seguro."
                ),
            ),
            KnowledgeDocument(
                title="Politicas Itau - governanca e integridade",
                source=POLICIES_SOURCE,
                text=(
                    "A pagina de politicas de relacoes com investidores do Itau concentra documentos "
                    "institucionais relacionados a governanca corporativa, integridade, etica, ESG, "
                    "informacoes ao mercado, resultados, relatorios e documentos regulatorios."
                ),
            ),
            KnowledgeDocument(
                title="Politicas Itau - mercado e regulatorio",
                source=POLICIES_SOURCE,
                text=(
                    "As politicas e documentos institucionais do Itau apoiam consultas sobre perfil "
                    "corporativo, governanca, ratings, renda fixa, documentos regulatorios, empresas do "
                    "grupo e comunicacao com investidores."
                ),
            ),
        ]


class TariffPdfIngestor:
    def __init__(
        self,
        pdf_path: Path = TARIFF_PDF_PATH,
        chunk_size: int = 900,
        chunk_overlap: int = 120,
        cache_path: Path = Path(".runtime/knowledge_tariff_chunks.json"),
    ) -> None:
        self._pdf_path = pdf_path
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._cache_path = cache_path

    @traceable(name="Tariff PDF Ingestion", run_type="retriever")
    def load_documents(self) -> list[KnowledgeDocument]:
        if not self._pdf_path.exists():
            return []

        cached = self._load_cache()
        if cached:
            return cached

        try:
            from pypdf import PdfReader
        except ImportError:
            return []

        reader = PdfReader(str(self._pdf_path))
        documents: list[KnowledgeDocument] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = self._normalize_whitespace(page.extract_text() or "")
            if not text:
                continue
            for chunk_index, chunk in enumerate(self._split_text(text), start=1):
                documents.append(
                    KnowledgeDocument(
                        title=f"Tabela geral de tarifas PF - pagina {page_number} - trecho {chunk_index}",
                        source=TARIFF_PDF_SOURCE,
                        text=f"Pagina {page_number}. {chunk}",
                    )
                )
        self._write_cache(documents)
        return documents

    def _load_cache(self) -> list[KnowledgeDocument]:
        if not self._cache_path.exists():
            return []

        try:
            payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        if payload.get("pdf_signature") != self._pdf_signature():
            return []

        return [
            KnowledgeDocument(
                title=str(item["title"]),
                source=str(item["source"]),
                text=str(item["text"]),
            )
            for item in payload.get("documents", [])
        ]

    def _write_cache(self, documents: list[KnowledgeDocument]) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pdf_signature": self._pdf_signature(),
            "documents": [
                {
                    "title": document.title,
                    "source": document.source,
                    "text": document.text,
                }
                for document in documents
            ],
        }
        self._cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _pdf_signature(self) -> dict[str, int]:
        stat = self._pdf_path.stat()
        return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}

    def _split_text(self, text: str) -> list[str]:
        if len(text) <= self._chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self._chunk_size, len(text))
            chunks.append(text[start:end].strip())
            if end == len(text):
                break
            start = max(end - self._chunk_overlap, start + 1)
        return [chunk for chunk in chunks if chunk]

    def _normalize_whitespace(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()


def build_official_documents() -> list[KnowledgeDocument]:
    curated = CuratedCatalogLoader().load_documents()
    ingested = TariffPdfIngestor().load_documents()
    web_documents = OfficialWebSnapshotIngestor().load_documents()
    if settings.knowledge_store == "postgres":
        from app.services.knowledge.postgres_store import PostgresKnowledgeStore

        store = PostgresKnowledgeStore(settings.database_url, settings.knowledge_embedding_dimensions)
        store.sync(curated, source_chunks=web_documents + ingested)
        return store.load_documents()
    curated_sources = {document.source for document in curated}
    legacy_documents = [
        document
        for document in OFFICIAL_KNOWLEDGE_DOCUMENTS + web_documents + ingested
        if document.source not in curated_sources
    ]
    return curated + legacy_documents
