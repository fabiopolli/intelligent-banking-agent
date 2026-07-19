from __future__ import annotations

from app.services.knowledge.config import HELP_CENTER_SOURCE, POLICIES_SOURCE, TARIFF_PDF_SOURCE
from app.services.knowledge.schemas import RetrievedKnowledge
from app.services.knowledge.tokenization import tokenize


class LocalReranker:
    def rerank(self, query: str, candidates: list[RetrievedKnowledge]) -> list[RetrievedKnowledge]:
        query_terms = set(self._tokenize(query))
        ranked = [
            RetrievedKnowledge(
                title=candidate.title,
                source=candidate.source,
                text=candidate.text,
                score=candidate.score + self._intent_bonus(query_terms, candidate),
            )
            for candidate in candidates
        ]
        return sorted(ranked, key=lambda item: item.score, reverse=True)

    def _intent_bonus(self, query_terms: set[str], candidate: RetrievedKnowledge) -> float:
        candidate_terms = set(self._tokenize(f"{candidate.title} {candidate.text}"))
        bonus = 0.0

        if query_terms & {"tarifa", "tarifas", "pacote", "pacotes", "saque", "servicos"}:
            if candidate.source == TARIFF_PDF_SOURCE:
                bonus += 2.0
            if candidate_terms & {"valor", "individual", "pacote", "servicos", "vigencia"}:
                bonus += 0.8

        if query_terms & {"whatsapp", "chat", "atendimento", "duvidas"}:
            if candidate.source == HELP_CENTER_SOURCE:
                bonus += 2.0

        if query_terms & {"politica", "politicas", "governanca", "integridade", "etica"}:
            if candidate.source == POLICIES_SOURCE:
                bonus += 2.0

        overlap = len(query_terms & candidate_terms)
        bonus += min(overlap * 0.25, 1.5)
        return bonus

    def _tokenize(self, text: str) -> list[str]:
        return tokenize(text)
