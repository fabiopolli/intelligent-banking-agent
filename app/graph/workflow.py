from __future__ import annotations

from app.graph.state import WorkflowNode, WorkflowRoute, WorkflowState
from app.schemas.auth import AuthContext
from app.schemas.harness import HarnessResponse
from app.schemas.messages import ChatRequest
from app.schemas.outbound import PixCreateRequest
from app.services.orchestrator import DemoOrchestrator, PendingPixOperation


class DemoWorkflowGraph:
    def __init__(self, orchestrator: DemoOrchestrator) -> None:
        self._orchestrator = orchestrator

    def invoke(
        self,
        payload: ChatRequest,
        auth: AuthContext,
        route: WorkflowRoute,
        pix_request: PixCreateRequest | None = None,
        pending_operation: PendingPixOperation | None = None,
    ) -> HarnessResponse:
        state = self._build_state(payload, auth, route)
        node = state["next_node"]

        if node == "emergency_node":
            return self._orchestrator.emergency(payload)
        if node == "core_banking_limit_node":
            return self._orchestrator.core_banking_limit(payload, auth)
        if node == "core_banking_balance_node":
            return self._orchestrator.core_banking_balance(payload, auth)
        if node == "transaction_node":
            if pending_operation is not None:
                return self._orchestrator.transaction_resume(payload, auth, pending_operation)
            if pix_request is None:
                raise ValueError("Pix request is required for transaction execution.")
            return self._orchestrator.transaction_execute(payload.session_id, pix_request)
        return self._orchestrator.faq_fast_path(payload.session_id)

    def checkpoint(self, session_id: str) -> HarnessResponse:
        return self._orchestrator.transaction_checkpoint(session_id)

    def _build_state(self, payload: ChatRequest, auth: AuthContext, route: WorkflowRoute) -> WorkflowState:
        return {
            "payload": payload,
            "auth": auth,
            "route": route,
            "next_node": self._resolve_node(route),
        }

    def _resolve_node(self, route: WorkflowRoute) -> WorkflowNode:
        if route == "emergency":
            return "emergency_node"
        if route == "core_banking_limit":
            return "core_banking_limit_node"
        if route == "core_banking_balance":
            return "core_banking_balance_node"
        if route == "transaction":
            return "transaction_node"
        return "faq_node"
