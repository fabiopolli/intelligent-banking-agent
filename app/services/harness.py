from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings
from app.schemas.auth import AuthContext
from app.schemas.harness import HarnessResponse
from app.schemas.messages import ChatRequest
from app.schemas.outbound import PixCreateRequest
from app.security.guardrails import GuardrailsService
from app.security.rbac import RBACService
from app.services.customer_support import CustomerSupportService
from app.services.intent_router import IntentRouter
from app.services.mock_bank import mock_bank_service
from app.services.response_builder import ResponseBuilder


@dataclass
class PendingPixOperation:
    customer_id: str
    amount: float
    destination_key: str


class DemoHarness:
    def __init__(
        self,
        router: IntentRouter | None = None,
        response_builder: ResponseBuilder | None = None,
        rbac_service: RBACService | None = None,
        guardrails_service: GuardrailsService | None = None,
    ) -> None:
        self._router = router or IntentRouter()
        self._response_builder = response_builder or ResponseBuilder()
        self._rbac_service = rbac_service or RBACService()
        self._guardrails_service = guardrails_service or GuardrailsService()
        self._pending_pix_operations: dict[str, PendingPixOperation] = {}

    def handle_message(self, payload: ChatRequest) -> dict:
        self._guardrails_service.validate_message(payload.message)
        if self._is_confirmation_message(payload.message):
            response = self._resume_pending_operation(payload)
            return response.model_dump()
        route = self._router.classify(payload.message)
        response = self._dispatch(route, payload)
        return response.model_dump()

    def _dispatch(self, route: str, payload: ChatRequest) -> HarnessResponse:
        auth = AuthContext(customer_id=payload.customer_id, role=payload.role)

        if route == "emergency":
            mock_bank_service.block_card(payload.customer_id)
            profile = mock_bank_service.get_customer_profile(payload.customer_id)
            return self._response_builder.emergency(
                payload.session_id,
                CustomerSupportService.require_profile(profile),
            )

        if route == "core_banking_limit":
            self._rbac_service.validate_owner_access(auth, payload.customer_id)
            profile = mock_bank_service.get_customer_profile(payload.customer_id)
            return self._response_builder.limit(
                payload.session_id,
                CustomerSupportService.require_profile(profile),
            )

        if route == "core_banking_balance":
            self._rbac_service.validate_owner_access(auth, payload.customer_id)
            balance = mock_bank_service.get_balance(payload.customer_id)
            return self._response_builder.balance(
                payload.session_id,
                CustomerSupportService.require_balance(balance),
            )

        if route == "transaction":
            pix_request = self._build_pix_request(payload)
            if pix_request.amount >= settings.hitl_pix_threshold:
                self._pending_pix_operations[payload.session_id] = PendingPixOperation(
                    customer_id=payload.customer_id,
                    amount=pix_request.amount,
                    destination_key=pix_request.destination_key,
                )
                return self._response_builder.transaction_checkpoint(payload.session_id)
            result = mock_bank_service.create_pix(pix_request)
            return self._response_builder.transaction_success(payload.session_id, float(result["balance"]))

        return self._response_builder.faq_fast_path(payload.session_id)

    def _resume_pending_operation(self, payload: ChatRequest) -> HarnessResponse:
        pending = self._pending_pix_operations.get(payload.session_id)
        if pending is None:
            raise ValueError("Nao existe operacao pendente para confirmacao nesta sessao.")

        self._rbac_service.validate_owner_access(
            AuthContext(customer_id=payload.customer_id, role=payload.role),
            pending.customer_id,
        )
        result = mock_bank_service.create_pix(
            PixCreateRequest(
                customer_id=pending.customer_id,
                amount=pending.amount,
                destination_key=pending.destination_key,
            )
        )
        self._pending_pix_operations.pop(payload.session_id, None)
        return self._response_builder.transaction_success(payload.session_id, float(result["balance"]))

    def _build_pix_request(self, payload: ChatRequest) -> PixCreateRequest:
        amount = self._extract_amount(payload.message)
        return PixCreateRequest(
            customer_id=payload.customer_id,
            amount=amount,
            destination_key="demo-chave-pix",
        )

    def _extract_amount(self, message: str) -> float:
        normalized = message.lower().replace("r$", "").replace(".", "").replace(",", ".")
        match = re.search(r"(\d+(?:\.\d+)?)", normalized)
        if match is None:
            return settings.hitl_pix_threshold
        return float(match.group(1))

    def _is_confirmation_message(self, message: str) -> bool:
        normalized = message.lower().strip()
        return normalized in {"confirmo", "confirmar", "sim, confirmo", "pode confirmar"}
