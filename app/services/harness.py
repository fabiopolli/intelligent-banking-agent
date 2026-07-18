from __future__ import annotations

import re

from app.config import settings
from app.schemas.auth import AuthContext
from app.schemas.harness import HarnessResponse
from app.schemas.messages import ChatRequest
from app.schemas.outbound import PixCreateRequest
from app.security.guardrails import GuardrailsService
from app.security.rbac import RBACService
from app.services.intent_router import IntentRouter
from app.services.orchestrator import DemoOrchestrator, PendingPixOperation
from app.services.response_builder import ResponseBuilder


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
        self._orchestrator = DemoOrchestrator(self._response_builder, self._rbac_service)
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
            return self._orchestrator.emergency(payload)

        if route == "core_banking_limit":
            return self._orchestrator.core_banking_limit(payload, auth)

        if route == "core_banking_balance":
            return self._orchestrator.core_banking_balance(payload, auth)

        if route == "transaction":
            pix_request = self._build_pix_request(payload)
            if pix_request.amount >= settings.hitl_pix_threshold:
                self._pending_pix_operations[payload.session_id] = PendingPixOperation(
                    customer_id=payload.customer_id,
                    amount=pix_request.amount,
                    destination_key=pix_request.destination_key,
                )
                return self._orchestrator.transaction_checkpoint(payload.session_id)
            return self._orchestrator.transaction_execute(payload.session_id, pix_request)

        return self._orchestrator.faq_fast_path(payload.session_id)

    def _resume_pending_operation(self, payload: ChatRequest) -> HarnessResponse:
        pending = self._pending_pix_operations.get(payload.session_id)
        if pending is None:
            raise ValueError("Nao existe operacao pendente para confirmacao nesta sessao.")

        response = self._orchestrator.transaction_resume(
            payload,
            AuthContext(customer_id=payload.customer_id, role=payload.role),
            pending,
        )
        self._pending_pix_operations.pop(payload.session_id, None)
        return response

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
