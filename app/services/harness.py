from __future__ import annotations

from app.schemas.auth import AuthContext
from app.schemas.harness import HarnessResponse
from app.schemas.messages import ChatRequest
from app.security.guardrails import GuardrailsService
from app.security.rbac import RBACService
from app.services.customer_support import CustomerSupportService
from app.services.intent_router import IntentRouter
from app.services.mock_bank import mock_bank_service
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

    def handle_message(self, payload: ChatRequest) -> dict:
        self._guardrails_service.validate_message(payload.message)
        route = self._router.classify(payload.message)
        response = self._dispatch(route, payload)
        return response.model_dump()

    def _dispatch(self, route: str, payload: ChatRequest) -> HarnessResponse:
        auth = AuthContext(customer_id=payload.customer_id, role=payload.role)

        if route == "emergency":
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
            return self._response_builder.transaction(payload.session_id)

        return self._response_builder.faq_fast_path(payload.session_id)
