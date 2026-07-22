from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from app.schemas.outbound import (
    AuditEventResponse,
    BalanceResponse,
    CardLimitUpdateRequest,
    CustomerProfileResponse,
    PixCreateRequest,
)
from app.services.audit_log import audit_log_service


@dataclass
class CustomerState:
    customer_id: str
    name: str
    segment: str
    card_status: str
    card_limit: float
    available_limit: float
    balance: float
    credit_score: int
    history: list[dict] = field(default_factory=list)


class MockBankService:
    def __init__(self) -> None:
        self._baseline = {
            "123": CustomerState(
                customer_id="123",
                name="Fabio de Melo",
                segment="Personnalite",
                card_status="ACTIVE",
                card_limit=10000.0,
                available_limit=10000.0,
                balance=25000.0,
                credit_score=820,
            ),
            "456": CustomerState(
                customer_id="456",
                name="Gerardo da Silva",
                segment="Uniclass",
                card_status="ACTIVE",
                card_limit=5000.0,
                available_limit=5000.0,
                balance=8000.0,
                credit_score=740,
            ),
        }
        self._customers = deepcopy(self._baseline)

    def reset(self) -> None:
        self._customers = deepcopy(self._baseline)

    def get_customer_profile(self, customer_id: str) -> CustomerProfileResponse | None:
        customer = self._customers.get(customer_id)
        if customer is None:
            return None
        return CustomerProfileResponse(
            customer_id=customer.customer_id,
            name=customer.name,
            segment=customer.segment,
            card_status=customer.card_status,
            card_limit=customer.card_limit,
            available_limit=customer.available_limit,
            credit_score=customer.credit_score,
        )

    def get_balance(self, customer_id: str) -> BalanceResponse | None:
        customer = self._customers.get(customer_id)
        if customer is None:
            return None
        return BalanceResponse(customer_id=customer.customer_id, balance=customer.balance)

    def update_card_limit(self, payload: CardLimitUpdateRequest) -> dict:
        customer = self._require_customer(payload.customer_id)
        used_limit = max(customer.card_limit - customer.available_limit, 0.0)
        customer.card_limit = payload.new_limit
        customer.available_limit = max(payload.new_limit - used_limit, 0.0)
        customer.history.append({"action": "LIMIT_CHANGE", "new_limit": payload.new_limit})
        audit_log_service.append(
            customer.customer_id,
            "LIMIT_CHANGE",
            {
                "new_limit": payload.new_limit,
                "available_limit": customer.available_limit,
            },
        )
        return {
            "customer_id": customer.customer_id,
            "card_limit": customer.card_limit,
            "available_limit": customer.available_limit,
        }

    def create_pix(self, payload: PixCreateRequest) -> dict:
        customer = self._require_customer(payload.customer_id)
        if payload.amount > customer.balance:
            raise ValueError("Saldo insuficiente para realizar o PIX.")

        customer.balance -= payload.amount
        customer.history.append(
            {
                "action": "PIX",
                "amount": payload.amount,
                "destination_key": payload.destination_key,
            }
        )
        audit_log_service.append(
            customer.customer_id,
            "PIX",
            {
                "amount": payload.amount,
                "destination_key": payload.destination_key,
                "resulting_balance": customer.balance,
            },
        )
        return {
            "customer_id": customer.customer_id,
            "balance": customer.balance,
            "status": "SUCCESS",
        }

    def block_card(self, customer_id: str) -> dict:
        customer = self._require_customer(customer_id)
        customer.card_status = "BLOCKED"
        customer.history.append({"action": "CARD_BLOCKED"})
        audit_log_service.append(
            customer.customer_id,
            "CARD_BLOCKED",
            {
                "card_status": customer.card_status,
            },
        )
        return {"customer_id": customer.customer_id, "card_status": customer.card_status}

    def get_service_history(self, customer_id: str) -> list[dict]:
        customer = self._require_customer(customer_id)
        return deepcopy(customer.history)

    def get_audit_events(self, customer_id: str) -> list[AuditEventResponse]:
        events = audit_log_service.list_by_customer(customer_id)
        return [AuditEventResponse.model_validate(event) for event in events]

    def _require_customer(self, customer_id: str) -> CustomerState:
        customer = self._customers.get(customer_id)
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found.")
        return customer


mock_bank_service = MockBankService()
