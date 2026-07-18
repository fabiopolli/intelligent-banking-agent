from __future__ import annotations

from app.schemas.outbound import BalanceResponse, CustomerProfileResponse


class CustomerSupportService:
    @staticmethod
    def require_profile(profile: CustomerProfileResponse | None) -> CustomerProfileResponse:
        if profile is None:
            raise ValueError("Customer not found.")
        return profile

    @staticmethod
    def require_balance(balance: BalanceResponse | None) -> BalanceResponse:
        if balance is None:
            raise ValueError("Customer not found.")
        return balance
