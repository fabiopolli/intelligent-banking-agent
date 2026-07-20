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
from app.services.knowledge.llm import GroundedFaqSynthesizer, build_grounded_faq_synthesizer
from app.services.knowledge.reranker import LocalReranker
from app.services.knowledge.retriever import LocalHybridRetriever
from app.services.knowledge.schemas import RetrievedKnowledge


class GroundedKnowledgeService:
    def __init__(
        self,
        retriever: LocalHybridRetriever | None = None,
        reranker: LocalReranker | None = None,
        synthesizer: GroundedFaqSynthesizer | None = None,
    ) -> None:
        self._retriever = retriever or LocalHybridRetriever()
        self._reranker = reranker or LocalReranker()
        self._synthesizer = synthesizer if synthesizer is not None else build_grounded_faq_synthesizer()
        self._tariff_answers = TariffAnswerBuilder(self._retriever.documents)

    def answer(self, query: str) -> tuple[str, list[str]]:
        result = self.answer_with_trace(query)
        return result["message"], result["sources"]

    def answer_with_trace(self, query: str) -> dict:
        tools_called = ["classify_documental_query"]
        if not self._is_supported_documental_query(query):
            message = (
                "Nao encontrei contexto oficial suficiente para responder com seguranca. "
                "Posso seguir por atendimento humano ou por uma fonte oficial mais especifica."
            )
            return self._answer_payload(message, [], tools_called, [], None)

        tools_called.extend(["hybrid_retrieve", "local_rerank"])
        retrieved = self._reranker.rerank(query, self._retriever.retrieve(query, top_k=6))[:2]
        if not retrieved or retrieved[0].score < 0.65:
            if self._is_tariff_query(query):
                primary = self._default_tariff_reference()
                tools_called.append("controlled_tariff_answer_builder")
                return self._answer_payload(
                    self._tariff_answers.build(query, primary),
                    [TARIFF_PDF_SOURCE],
                    tools_called,
                    [primary],
                    None,
                )

            message = (
                "Nao encontrei contexto oficial suficiente para responder com seguranca. "
                "Posso seguir por atendimento humano ou por uma fonte oficial mais especifica."
            )
            return self._answer_payload(message, [], tools_called, retrieved, None)

        primary = retrieved[0]
        excerpt = self._compact_excerpt(primary.text)
        if self._synthesizer is not None:
            tools_called.append("grounded_faq_synthesizer")
            message = self._synthesizer.synthesize(query, retrieved)
            llm_trace = getattr(self._synthesizer, "last_trace", {}) or {}
            if self._is_tariff_query(query) and llm_trace.get("fallback_used"):
                tools_called.append("controlled_tariff_answer_builder")
                message = self._tariff_answers.build(query, primary)
        elif self._is_tariff_query(query):
            tools_called.append("controlled_tariff_answer_builder")
            message = self._tariff_answers.build(query, primary)
            llm_trace = None
        elif "politica" in query.lower() or "governanca" in query.lower():
            message = (
                "Para politicas institucionais, encontrei a fonte oficial de relacoes com investidores "
                f"e politicas do Itau. Trecho usado: {excerpt}"
            )
            llm_trace = None
        else:
            message = (
                "Encontrei uma orientacao oficial de atendimento Itau relacionada a sua pergunta. "
                f"Trecho usado: {excerpt}"
            )
            llm_trace = None

        sources = list(dict.fromkeys(item.source for item in retrieved))
        return self._answer_payload(message, sources, tools_called, retrieved, llm_trace)

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
            "grounded_faq_synthesizer": self._synthesizer.provider_name if self._synthesizer else "disabled",
        }

    def _compact_excerpt(self, text: str, limit: int = 220) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit].rstrip()}..."

    def _answer_payload(
        self,
        message: str,
        sources: list[str],
        tools_called: list[str],
        retrieved: list[RetrievedKnowledge],
        llm_trace: dict | None,
    ) -> dict:
        return {
            "message": message,
            "sources": sources,
            "observability": {
                "tools_called": tools_called,
                "retrieval": {
                    "candidate_count": len(retrieved),
                    "sources": sources,
                    "approved_context": [
                        {
                            "title": item.title,
                            "source": item.source,
                            "score": item.score,
                            "excerpt": self._compact_excerpt(item.text, limit=360),
                        }
                        for item in retrieved
                    ],
                },
                "llm": llm_trace
                or {
                    "provider": "disabled",
                    "model": None,
                    "fallback_used": False,
                    "token_usage": None,
                    "prompt": None,
                    "approved_context": [],
                },
            },
        }

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
