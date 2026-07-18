from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeDocument:
    title: str
    source: str
    text: str


@dataclass(frozen=True)
class RetrievedKnowledge:
    title: str
    source: str
    text: str
    score: float


OFFICIAL_KNOWLEDGE_DOCUMENTS = [
    KnowledgeDocument(
        title="Atendimento Itau - canais digitais",
        source="https://www.itau.com.br/atendimento-itau/para-voce",
        text=(
            "O atendimento Itau para clientes pessoa fisica concentra orientacoes de canais digitais, "
            "segunda via, ajuda com cartoes, seguranca, conta, pagamentos e suporte para uso do app."
        ),
    ),
    KnowledgeDocument(
        title="Tabela geral de tarifas PF",
        source=".docs/tabela_geral_de_tarifas_pf_pdf.pdf",
        text=(
            "A tabela geral de tarifas pessoa fisica e a fonte oficial local para validar valores de "
            "tarifas, pacotes de servicos, segunda via, saques, transferencias, manutencao de conta e "
            "outros servicos bancarios sujeitos a cobranca."
        ),
    ),
    KnowledgeDocument(
        title="Politicas e relacoes com investidores Itau",
        source="https://www.itau.com.br/relacoes-com-investidores/politicas/",
        text=(
            "As politicas publicadas pelo Itau reunem documentos institucionais de governanca, conduta, "
            "integridade, seguranca e relacionamento com partes interessadas."
        ),
    ),
]


class LocalHybridRetriever:
    def __init__(self, documents: list[KnowledgeDocument] | None = None) -> None:
        self._documents = documents or OFFICIAL_KNOWLEDGE_DOCUMENTS
        self._tokenized_documents = [self._tokenize(document.text) for document in self._documents]
        self._document_frequency = self._build_document_frequency()

    def retrieve(self, query: str, top_k: int = 2) -> list[RetrievedKnowledge]:
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        ranked = [
            RetrievedKnowledge(
                title=document.title,
                source=document.source,
                text=document.text,
                score=self._score(query_terms, self._tokenized_documents[index], document.text),
            )
            for index, document in enumerate(self._documents)
        ]
        return [item for item in sorted(ranked, key=lambda item: item.score, reverse=True)[:top_k] if item.score > 0]

    def _score(self, query_terms: list[str], document_terms: list[str], document_text: str) -> float:
        lexical_score = self._bm25_like_score(query_terms, document_terms)
        semantic_score = self._semantic_overlap_score(query_terms, document_terms)
        phrase_bonus = self._phrase_bonus(query_terms, document_text)
        return lexical_score + semantic_score + phrase_bonus

    def _bm25_like_score(self, query_terms: list[str], document_terms: list[str]) -> float:
        score = 0.0
        document_length = max(len(document_terms), 1)
        average_length = max(
            sum(len(terms) for terms in self._tokenized_documents) / max(len(self._tokenized_documents), 1),
            1,
        )

        for term in set(query_terms):
            term_frequency = document_terms.count(term)
            if term_frequency == 0:
                continue
            inverse_document_frequency = math.log(
                1 + (len(self._documents) - self._document_frequency.get(term, 0) + 0.5)
                / (self._document_frequency.get(term, 0) + 0.5)
            )
            denominator = term_frequency + 1.2 * (1 - 0.75 + 0.75 * document_length / average_length)
            score += inverse_document_frequency * ((term_frequency * 2.2) / denominator)
        return score

    def _semantic_overlap_score(self, query_terms: list[str], document_terms: list[str]) -> float:
        query_set = set(query_terms)
        document_set = set(document_terms)
        if not query_set or not document_set:
            return 0.0
        return len(query_set & document_set) / len(query_set | document_set)

    def _phrase_bonus(self, query_terms: list[str], document_text: str) -> float:
        normalized_document = " ".join(self._tokenize(document_text))
        normalized_query = " ".join(query_terms)
        if normalized_query and normalized_query in normalized_document:
            return 1.0
        return 0.0

    def _build_document_frequency(self) -> dict[str, int]:
        frequency: dict[str, int] = {}
        for terms in self._tokenized_documents:
            for term in set(terms):
                frequency[term] = frequency.get(term, 0) + 1
        return frequency

    def _tokenize(self, text: str) -> list[str]:
        normalized = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("ascii")
        return [token for token in re.findall(r"[a-z0-9]+", normalized) if len(token) > 2]


class GroundedKnowledgeService:
    def __init__(self, retriever: LocalHybridRetriever | None = None) -> None:
        self._retriever = retriever or LocalHybridRetriever()

    def answer(self, query: str) -> tuple[str, list[str]]:
        retrieved = self._retriever.retrieve(query)
        if not retrieved or retrieved[0].score < 0.15:
            return (
                "Nao encontrei contexto oficial suficiente para responder com seguranca. "
                "Posso seguir por atendimento humano ou por uma fonte oficial mais especifica.",
                [],
            )

        primary = retrieved[0]
        if "tarifa" in query.lower() or "pacote" in query.lower():
            message = (
                "Para tarifas e pacotes, a resposta deve ser conferida na tabela geral de tarifas PF. "
                "Nesta demo local, encontrei a fonte oficial preparada para grounding documental."
            )
        elif "politica" in query.lower() or "governanca" in query.lower():
            message = (
                "Para politicas institucionais, encontrei a fonte oficial de relacoes com investidores "
                "e politicas do Itau usada como base de grounding."
            )
        else:
            message = (
                "Encontrei uma orientacao oficial de atendimento Itau relacionada a sua pergunta. "
                "Use a fonte retornada para validar o detalhe operacional."
            )

        sources = [item.source for item in retrieved]
        return message, sources


knowledge_service = GroundedKnowledgeService()
