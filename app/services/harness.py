from __future__ import annotations

import re

from app.config import settings
from app.graph.workflow import DemoWorkflowGraph
from app.schemas.auth import AuthContext
from app.schemas.harness import HarnessResponse
from app.schemas.messages import ChatRequest
from app.schemas.outbound import PixCreateRequest
from app.security.guardrails import GuardrailsService
from app.security.rbac import RBACService
from app.services.checkpoint_store import CheckpointStore, checkpoint_store
from app.services.intent_router import IntentRouter
from app.services.observability import traceable
from app.services.orchestrator import DemoOrchestrator, PendingPixOperation
from app.services.response_builder import ResponseBuilder
from app.services.trace_store import trace_store


class DemoHarness:
    def __init__(
        self,
        router: IntentRouter | None = None,
        response_builder: ResponseBuilder | None = None,
        rbac_service: RBACService | None = None,
        guardrails_service: GuardrailsService | None = None,
        checkpoints: CheckpointStore | None = None,
    ) -> None:
        self._router = router or IntentRouter()
        self._response_builder = response_builder or ResponseBuilder()
        self._rbac_service = rbac_service or RBACService()
        self._guardrails_service = guardrails_service or GuardrailsService()
        self._orchestrator = DemoOrchestrator(self._response_builder, self._rbac_service)
        self._workflow_graph = DemoWorkflowGraph(self._orchestrator)
        self._checkpoints = checkpoints or checkpoint_store

    def handle_message(self, payload: ChatRequest) -> dict:
        response = self._handle_message(payload)
        response_payload = response.model_dump()
        trace_store.record(payload.session_id, response_payload)
        return response_payload

    @traceable(name="Agent Harness", run_type="chain")
    def _handle_message(self, payload: ChatRequest) -> HarnessResponse:
        self._guardrails_service.validate_message(payload.message)
        if self._is_confirmation_message(payload.message):
            return self._resume_pending_operation(payload)
        route = self._classify_intent(payload.message)
        return self._dispatch(route, payload)

    @traceable(name="Intent Router", run_type="chain")
    def _classify_intent(self, message: str) -> str:
        return self._router.classify(message)

    def _dispatch(self, route: str, payload: ChatRequest) -> HarnessResponse:
        auth = AuthContext(customer_id=payload.customer_id, role=payload.role)

        if route == "transaction":
            pix_request = self._build_pix_request(payload)
            if pix_request.amount >= settings.hitl_pix_threshold:
                self._checkpoints.save_pending_pix(
                    payload.session_id,
                    PendingPixOperation(
                        customer_id=payload.customer_id,
                        amount=pix_request.amount,
                        destination_key=pix_request.destination_key,
                    ),
                )
                return self._workflow_graph.checkpoint(payload.session_id)
            return self._workflow_graph.invoke(payload, auth, route, pix_request=pix_request)

        return self._workflow_graph.invoke(payload, auth, route)

    def _resume_pending_operation(self, payload: ChatRequest) -> HarnessResponse:
        pending = self._checkpoints.get_pending_pix(payload.session_id)
        if pending is None:
            raise ValueError("Nao existe operacao pendente para confirmacao nesta sessao.")

        response = self._workflow_graph.invoke(
            payload,
            AuthContext(customer_id=payload.customer_id, role=payload.role),
            "transaction",
            pending_operation=pending,
        )
        self._checkpoints.consume_pending_pix(payload.session_id)
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
