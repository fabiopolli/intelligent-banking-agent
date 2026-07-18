from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field

from app.schemas.outbound import (
    BalanceResponse,
    CardLimitUpdateRequest,
    CustomerProfileResponse,
    PixCreateRequest,
)


@dataclass
class CustomerState:
    customer_id: str
    name: str
    segment: str
    card_status: str
    card_limit: float
    available_limit: float
    balance: float
    history: list[dict] = field(default_factory=list)


class MockBankService:
    def __init__(self) -> None:
        self._baseline = {
            "123": CustomerState(
                customer_id="123",
                name="Fabio Polli",
                segment="Personnalite",
                card_status="ACTIVE",
                card_limit=10000.0,
                available_limit=10000.0,
                balance=25000.0,
            )
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
        )

    def get_balance(self, customer_id: str) -> BalanceResponse | None:
        customer = self._customers.get(customer_id)
        if customer is None:
            return None
        return BalanceResponse(customer_id=customer.customer_id, balance=customer.balance)

    def update_card_limit(self, payload: CardLimitUpdateRequest) -> dict:
        customer = self._require_customer(payload.customer_id)
        customer.card_limit = payload.new_limit
        customer.available_limit = min(customer.available_limit, payload.new_limit)
        customer.history.append({"action": "LIMIT_CHANGE", "new_limit": payload.new_limit})
        return {
            "customer_id": customer.customer_id,
            "card_limit": customer.card_limit,
            "available_limit": customer.available_limit,
        }

    def create_pix(self, payload: PixCreateRequest) -> dict:
        customer = self._require_customer(payload.customer_id)
        customer.balance -= payload.amount
        customer.history.append(
            {
                "action": "PIX",
                "amount": payload.amount,
                "destination_key": payload.destination_key,
            }
        )
        return {
            "customer_id": customer.customer_id,
            "balance": customer.balance,
            "status": "SUCCESS",
        }

    def _require_customer(self, customer_id: str) -> CustomerState:
        customer = self._customers.get(customer_id)
        if customer is None:
            raise ValueError(f"Customer {customer_id} not found.")
        return customer


mock_bank_service = MockBankService()
