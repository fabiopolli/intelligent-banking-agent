from __future__ import annotations

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


@dataclass(frozen=True)
class TariffGuidance:
    page_hint: str
    message: str
