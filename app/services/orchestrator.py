from __future__ import annotations

from dataclasses import dataclass

from app.schemas.auth import AuthContext
from app.schemas.harness import HarnessResponse
from app.schemas.messages import ChatRequest
from app.schemas.outbound import PixCreateRequest
from app.security.rbac import RBACService
from app.services.customer_support import CustomerSupportService
from app.services.knowledge_base import GroundedKnowledgeService, knowledge_service
from app.services.mock_bank import mock_bank_service
from app.services.observability import traceable
from app.services.response_builder import ResponseBuilder


@dataclass
class PendingPixOperation:
    customer_id: str
    amount: float
    destination_key: str


class EmergencyNode:
    def __init__(self, response_builder: ResponseBuilder) -> None:
        self._response_builder = response_builder

    def handle(self, payload: ChatRequest) -> HarnessResponse:
        return self._handle(payload)

    @traceable(name="Emergency Node", run_type="tool")
    def _handle(self, payload: ChatRequest) -> HarnessResponse:
        mock_bank_service.block_card(payload.customer_id)
        profile = mock_bank_service.get_customer_profile(payload.customer_id)
        return self._response_builder.emergency(
            payload.session_id,
            CustomerSupportService.require_profile(profile),
        )


class CoreBankingNode:
    def __init__(self, response_builder: ResponseBuilder, rbac_service: RBACService) -> None:
        self._response_builder = response_builder
        self._rbac_service = rbac_service

    def handle_limit(self, payload: ChatRequest, auth: AuthContext) -> HarnessResponse:
        return self._handle_limit(payload, auth)

    @traceable(name="Core Banking Limit Node", run_type="tool")
    def _handle_limit(self, payload: ChatRequest, auth: AuthContext) -> HarnessResponse:
        self._rbac_service.validate_owner_access(auth, payload.customer_id)
        profile = mock_bank_service.get_customer_profile(payload.customer_id)
        return self._response_builder.limit(
            payload.session_id,
            CustomerSupportService.require_profile(profile),
        )

    def handle_balance(self, payload: ChatRequest, auth: AuthContext) -> HarnessResponse:
        return self._handle_balance(payload, auth)

    @traceable(name="Core Banking Balance Node", run_type="tool")
    def _handle_balance(self, payload: ChatRequest, auth: AuthContext) -> HarnessResponse:
        self._rbac_service.validate_owner_access(auth, payload.customer_id)
        balance = mock_bank_service.get_balance(payload.customer_id)
        return self._response_builder.balance(
            payload.session_id,
            CustomerSupportService.require_balance(balance),
        )


class TransactionNode:
    def __init__(self, response_builder: ResponseBuilder, rbac_service: RBACService) -> None:
        self._response_builder = response_builder
        self._rbac_service = rbac_service

    def create_checkpoint(self, session_id: str) -> HarnessResponse:
        return self._create_checkpoint(session_id)

    @traceable(name="HITL Checkpoint", run_type="tool")
    def _create_checkpoint(self, session_id: str) -> HarnessResponse:
        return self._response_builder.transaction_checkpoint(session_id)

    def execute_pix(self, session_id: str, pix_request: PixCreateRequest) -> HarnessResponse:
        return self._execute_pix(session_id, pix_request)

    @traceable(name="PIX Tool", run_type="tool")
    def _execute_pix(self, session_id: str, pix_request: PixCreateRequest) -> HarnessResponse:
        result = mock_bank_service.create_pix(pix_request)
        return self._response_builder.transaction_success(session_id, float(result["balance"]))

    def resume_pix(
        self,
        payload: ChatRequest,
        auth: AuthContext,
        pending_operation: PendingPixOperation,
    ) -> HarnessResponse:
        self._rbac_service.validate_owner_access(auth, pending_operation.customer_id)
        return self.execute_pix(
            payload.session_id,
            PixCreateRequest(
                customer_id=pending_operation.customer_id,
                amount=pending_operation.amount,
                destination_key=pending_operation.destination_key,
            ),
        )


class FaqNode:
    def __init__(
        self,
        response_builder: ResponseBuilder,
        grounded_knowledge: GroundedKnowledgeService,
    ) -> None:
        self._response_builder = response_builder
        self._grounded_knowledge = grounded_knowledge

    def handle(self, payload: ChatRequest) -> HarnessResponse:
        return self._handle(payload)

    @traceable(name="Grounded Knowledge Node", run_type="retriever")
    def _handle(self, payload: ChatRequest) -> HarnessResponse:
        answer = self._grounded_knowledge.answer_with_trace(payload.message)
        return self._response_builder.grounded_knowledge(
            payload.session_id,
            answer["message"],
            answer["sources"],
            answer["observability"],
        )


class DemoOrchestrator:
    def __init__(
        self,
        response_builder: ResponseBuilder,
        rbac_service: RBACService,
        grounded_knowledge: GroundedKnowledgeService | None = None,
    ) -> None:
        self._emergency = EmergencyNode(response_builder)
        self._core_banking = CoreBankingNode(response_builder, rbac_service)
        self._transaction = TransactionNode(response_builder, rbac_service)
        self._faq = FaqNode(response_builder, grounded_knowledge or knowledge_service)

    def emergency(self, payload: ChatRequest) -> HarnessResponse:
        return self._emergency.handle(payload)

    def core_banking_limit(self, payload: ChatRequest, auth: AuthContext) -> HarnessResponse:
        return self._core_banking.handle_limit(payload, auth)

    def core_banking_balance(self, payload: ChatRequest, auth: AuthContext) -> HarnessResponse:
        return self._core_banking.handle_balance(payload, auth)

    def transaction_checkpoint(self, session_id: str) -> HarnessResponse:
        return self._transaction.create_checkpoint(session_id)

    def transaction_execute(self, session_id: str, pix_request: PixCreateRequest) -> HarnessResponse:
        return self._transaction.execute_pix(session_id, pix_request)

    def transaction_resume(
        self,
        payload: ChatRequest,
        auth: AuthContext,
        pending_operation: PendingPixOperation,
    ) -> HarnessResponse:
        return self._transaction.resume_pix(payload, auth, pending_operation)

    def faq_fast_path(self, payload: ChatRequest) -> HarnessResponse:
        return self._faq.handle(payload)
