from __future__ import annotations

import math

from app.services.knowledge.ingestion import build_official_documents
from app.services.knowledge.schemas import KnowledgeDocument, RetrievedKnowledge
from app.services.knowledge.tokenization import tokenize


class LocalHybridRetriever:
    def __init__(self, documents: list[KnowledgeDocument] | None = None) -> None:
        self._documents = documents or build_official_documents()
        self._tokenized_documents = [self._tokenize(document.text) for document in self._documents]
        self._document_frequency = self._build_document_frequency()

    @property
    def document_count(self) -> int:
        return len(self._documents)

    @property
    def sources(self) -> list[str]:
        return sorted({document.source for document in self._documents})

    @property
    def documents(self) -> list[KnowledgeDocument]:
        return list(self._documents)

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
        return tokenize(text)
