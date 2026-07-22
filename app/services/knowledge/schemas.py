from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class KnowledgeDocument:
    title: str
    source: str
    text: str
    knowledge_id: str = ""
    product: str = "general"
    topic: str = "general"
    audience: str = "all"
    version: int = 1
    status: str = "published"
    reviewed_at: str | None = None
    limitations: str = ""


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


@dataclass(frozen=True)
class TariffEntry:
    tariff_id: str
    source_id: str
    section_id: str
    page_number: int
    category: str
    service_name: str
    value_type: str
    effective_from: str
    status: str = "review_required"
    service_code: str = ""
    delivery_channel: str = ""
    statement_code: str = ""
    amount: Decimal | None = None
    minimum_amount: Decimal | None = None
    maximum_amount: Decimal | None = None
    percentage_min: Decimal | None = None
    percentage_max: Decimal | None = None
    currency: str = "BRL"
    billing_unit: str = ""
    charging_event: str = ""
    dimensions: dict[str, Any] | None = None
    confidence: Decimal | None = None
    reviewed_at: str | None = None


@dataclass(frozen=True)
class TariffRule:
    rule_id: str
    source_id: str
    page_number: int
    rule_code: str
    text: str
    effective_from: str
    status: str = "review_required"
