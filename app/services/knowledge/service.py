from __future__ import annotations

import re

from app.services.knowledge.answers import TariffAnswerBuilder
from app.services.knowledge.config import (
    DOCUMENTAL_QUERY_TERMS,
    HELP_CENTER_SOURCE,
    POLICIES_SOURCE,
    TARIFF_PDF_SOURCE,
    TARIFF_QUERY_TERMS,
)
from app.services.knowledge.reranker import LocalReranker
from app.services.knowledge.retriever import LocalHybridRetriever
from app.services.knowledge.schemas import RetrievedKnowledge


class GroundedKnowledgeService:
    def __init__(
        self,
        retriever: LocalHybridRetriever | None = None,
        reranker: LocalReranker | None = None,
    ) -> None:
        self._retriever = retriever or LocalHybridRetriever()
        self._reranker = reranker or LocalReranker()
        self._tariff_answers = TariffAnswerBuilder(self._retriever.documents)

    def answer(self, query: str) -> tuple[str, list[str]]:
        if not self._is_supported_documental_query(query):
            return (
                "Nao encontrei contexto oficial suficiente para responder com seguranca. "
                "Posso seguir por atendimento humano ou por uma fonte oficial mais especifica.",
                [],
            )

        retrieved = self._reranker.rerank(query, self._retriever.retrieve(query, top_k=6))[:2]
        if not retrieved or retrieved[0].score < 0.65:
            if self._is_tariff_query(query):
                primary = self._default_tariff_reference()
                return self._tariff_answers.build(query, primary), [TARIFF_PDF_SOURCE]

            return (
                "Nao encontrei contexto oficial suficiente para responder com seguranca. "
                "Posso seguir por atendimento humano ou por uma fonte oficial mais especifica.",
                [],
            )

        primary = retrieved[0]
        excerpt = self._compact_excerpt(primary.text)
        if self._is_tariff_query(query):
            message = self._tariff_answers.build(query, primary)
        elif "politica" in query.lower() or "governanca" in query.lower():
            message = (
                "Para politicas institucionais, encontrei a fonte oficial de relacoes com investidores "
                f"e politicas do Itau. Trecho usado: {excerpt}"
            )
        else:
            message = (
                "Encontrei uma orientacao oficial de atendimento Itau relacionada a sua pergunta. "
                f"Trecho usado: {excerpt}"
            )

        sources = list(dict.fromkeys(item.source for item in retrieved))
        return message, sources

    def status(self) -> dict:
        return {
            "document_count": self._retriever.document_count,
            "sources": self._retriever.sources,
            "pdf_ingested": TARIFF_PDF_SOURCE in self._retriever.sources,
            "web_sources_loaded": all(
                source in self._retriever.sources
                for source in [HELP_CENTER_SOURCE, POLICIES_SOURCE]
            ),
            "reranker": "local-intent-reranker",
        }

    def _compact_excerpt(self, text: str, limit: int = 220) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit].rstrip()}..."

    def _is_supported_documental_query(self, query: str) -> bool:
        query_terms = set(self._retriever._tokenize(query))
        return bool(query_terms & DOCUMENTAL_QUERY_TERMS)

    def _is_tariff_query(self, query: str) -> bool:
        query_terms = set(self._retriever._tokenize(query))
        return bool(query_terms & TARIFF_QUERY_TERMS)

    def _default_tariff_reference(self) -> RetrievedKnowledge:
        for document in self._retriever.documents:
            if document.source == TARIFF_PDF_SOURCE:
                return RetrievedKnowledge(
                    title=document.title,
                    source=document.source,
                    text=document.text,
                    score=0.0,
                )
        return RetrievedKnowledge(
            title="Tabela geral de tarifas PF",
            source=TARIFF_PDF_SOURCE,
            text="Tabela geral de tarifas PF do Itau.",
            score=0.0,
        )


knowledge_service = GroundedKnowledgeService()
