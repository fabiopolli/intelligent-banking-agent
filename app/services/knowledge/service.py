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
        ranked = self._reranker.rerank(query, self._retriever.retrieve(query, top_k=6))
        retrieved = self._select_grounded_contexts(ranked)
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
        if self._is_consignado_query(query):
            retrieved = [item for item in retrieved if "consignado" in item.source]
            tools_called.append("controlled_consignado_answer_builder")
            message = (
                "O consignado INSS nao tem uma taxa unica publicada para todos os clientes. "
                "Ele atende aposentados, pensionistas e outros beneficiarios que recebem pelo Itau, "
                "tenham margem disponivel e pode ter prazo de ate 108 meses. A taxa e o CET aparecem "
                "na simulacao vigente antes da contratacao."
            )
            llm_trace = None
        elif self._is_investment_query(query) and not self._is_specific_investment_tariff_query(query):
            retrieved = self._ensure_source_context(
                retrieved,
                "https://www.itau.com.br/investimentos",
            )
            retrieved = self._ensure_source_context(retrieved, TARIFF_PDF_SOURCE)
            tools_called.append("controlled_investment_answer_builder")
            message = (
                "Nos canais digitais elegiveis, o Itau informa taxa zero de custodia para renda "
                "variavel, renda fixa e Tesouro Direto, e corretagem zero para fundos imobiliarios. "
                "Fundos de investimento podem cobrar administracao conforme o produto: a tabela PF "
                "vigente desde 01/07/2026 indica faixas de 0,10% a 4,50% para fundos abertos e de "
                "0,30% a 4,50% para fundos fechados. Confira o regulamento do fundo antes de investir."
            )
            llm_trace = None
        elif self._is_tariff_query(query):
            tools_called.append("controlled_tariff_answer_builder")
            message = self._tariff_answers.build(query, primary)
            llm_trace = None
        elif self._synthesizer is not None:
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
        curated_documents = [
            document for document in self._retriever.documents if document.knowledge_id
        ]
        return {
            "document_count": self._retriever.document_count,
            "curated_document_count": len(curated_documents),
            "knowledge_store": self._retriever.store_name,
            "catalog_versions": sorted({document.version for document in curated_documents}),
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
            "message": self._with_conversation_follow_up(message),
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

    def _with_conversation_follow_up(self, message: str) -> str:
        follow_up = "Posso ajudar com mais alguma dúvida?"
        if follow_up.lower() in message.lower():
            return message
        return f"{message.rstrip()} {follow_up}"

    def _is_supported_documental_query(self, query: str) -> bool:
        query_terms = set(self._retriever._tokenize(query))
        return bool(query_terms & DOCUMENTAL_QUERY_TERMS)

    def _select_grounded_contexts(self, ranked: list[RetrievedKnowledge]) -> list[RetrievedKnowledge]:
        if not ranked:
            return []
        primary = ranked[0]
        minimum_score = max(0.65, primary.score * 0.35)
        return [item for item in ranked[:2] if item.score >= minimum_score]

    def _is_tariff_query(self, query: str) -> bool:
        query_terms = set(self._retriever._tokenize(query))
        return bool(query_terms & TARIFF_QUERY_TERMS)

    def _is_consignado_query(self, query: str) -> bool:
        query_terms = set(self._retriever._tokenize(query))
        return "consignado" in query_terms and bool(
            query_terms & {"aposentado", "aposentados", "pensionista", "pensionistas", "inss"}
        )

    def _is_investment_query(self, query: str) -> bool:
        query_terms = set(self._retriever._tokenize(query))
        return bool(
            query_terms
            & {"investimento", "investimentos", "fundo", "fundos", "tesouro", "custodia", "corretagem"}
        )

    def _is_specific_investment_tariff_query(self, query: str) -> bool:
        query_terms = set(self._retriever._tokenize(query))
        return bool(
            query_terms
            & {"custodia", "corretagem", "tesouro", "cripto", "performance", "carregamento", "escrow"}
        )

    def _is_tariff_navigation_query(self, query: str) -> bool:
        normalized = query.lower()
        return self._is_tariff_query(query) and any(
            phrase in normalized
            for phrase in ("onde consulto", "onde consultar", "onde encontro", "como consultar")
        )

    def _ensure_source_context(
        self,
        retrieved: list[RetrievedKnowledge],
        source: str,
    ) -> list[RetrievedKnowledge]:
        if any(item.source == source for item in retrieved):
            return retrieved
        for document in self._retriever.documents:
            if document.source == source:
                return retrieved + [
                    RetrievedKnowledge(
                        title=document.title,
                        source=document.source,
                        text=document.text,
                        score=1.0,
                    )
                ]
        return retrieved

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
