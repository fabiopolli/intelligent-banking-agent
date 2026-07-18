from __future__ import annotations

from typing import Any

from app.graph.state import WorkflowNode, WorkflowRoute, WorkflowState
from app.schemas.auth import AuthContext
from app.schemas.harness import HarnessResponse
from app.schemas.messages import ChatRequest
from app.schemas.outbound import PixCreateRequest
from app.services.orchestrator import DemoOrchestrator, PendingPixOperation

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # pragma: no cover - exercised through fallback path
    END = START = StateGraph = None


class DemoWorkflowGraph:
    def __init__(self, orchestrator: DemoOrchestrator) -> None:
        self._orchestrator = orchestrator
        self._compiled_graph = self._build_langgraph() if StateGraph is not None else None

    @property
    def uses_langgraph(self) -> bool:
        return self._compiled_graph is not None

    def invoke(
        self,
        payload: ChatRequest,
        auth: AuthContext,
        route: WorkflowRoute,
        pix_request: PixCreateRequest | None = None,
        pending_operation: PendingPixOperation | None = None,
    ) -> HarnessResponse:
        if self._compiled_graph is None:
            return self._invoke_fallback(payload, auth, route, pix_request, pending_operation)

        state = self._build_state(payload, auth, route, pix_request, pending_operation)
        result = self._compiled_graph.invoke(state)
        response = result.get("response")
        if response is None:
            raise ValueError("Workflow graph did not produce a response.")
        return response

    def checkpoint(self, session_id: str) -> HarnessResponse:
        return self._orchestrator.transaction_checkpoint(session_id)

    def _build_state(
        self,
        payload: ChatRequest,
        auth: AuthContext,
        route: WorkflowRoute,
        pix_request: PixCreateRequest | None = None,
        pending_operation: PendingPixOperation | None = None,
    ) -> WorkflowState:
        serialized_pending = None
        if pending_operation is not None:
            serialized_pending = {
                "customer_id": pending_operation.customer_id,
                "amount": pending_operation.amount,
                "destination_key": pending_operation.destination_key,
            }
        return {
            "payload": payload,
            "auth": auth,
            "route": route,
            "next_node": self._resolve_node(route),
            "response": None,
            "pix_request": pix_request,
            "pending_operation": serialized_pending,
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

    def _invoke_fallback(
        self,
        payload: ChatRequest,
        auth: AuthContext,
        route: WorkflowRoute,
        pix_request: PixCreateRequest | None,
        pending_operation: PendingPixOperation | None,
    ) -> HarnessResponse:
        state = self._build_state(payload, auth, route, pix_request, pending_operation)
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
        return self._orchestrator.faq_fast_path(payload)

    def _build_langgraph(self) -> Any:
        graph = StateGraph(WorkflowState)
        graph.add_node("faq_node", self._faq_node)
        graph.add_node("core_banking_limit_node", self._core_banking_limit_node)
        graph.add_node("core_banking_balance_node", self._core_banking_balance_node)
        graph.add_node("transaction_node", self._transaction_node)
        graph.add_node("emergency_node", self._emergency_node)

        graph.add_conditional_edges(START, self._route_from_state)
        graph.add_edge("faq_node", END)
        graph.add_edge("core_banking_limit_node", END)
        graph.add_edge("core_banking_balance_node", END)
        graph.add_edge("transaction_node", END)
        graph.add_edge("emergency_node", END)
        return graph.compile()

    def _route_from_state(self, state: WorkflowState) -> WorkflowNode:
        return state["next_node"]

    def _faq_node(self, state: WorkflowState) -> WorkflowState:
        return {"response": self._orchestrator.faq_fast_path(state["payload"])}

    def _core_banking_limit_node(self, state: WorkflowState) -> WorkflowState:
        return {
            "response": self._orchestrator.core_banking_limit(
                state["payload"],
                state["auth"],
            )
        }

    def _core_banking_balance_node(self, state: WorkflowState) -> WorkflowState:
        return {
            "response": self._orchestrator.core_banking_balance(
                state["payload"],
                state["auth"],
            )
        }

    def _transaction_node(self, state: WorkflowState) -> WorkflowState:
        if state["pending_operation"] is not None:
            pending = PendingPixOperation(
                customer_id=str(state["pending_operation"]["customer_id"]),
                amount=float(state["pending_operation"]["amount"]),
                destination_key=str(state["pending_operation"]["destination_key"]),
            )
            response = self._orchestrator.transaction_resume(
                state["payload"],
                state["auth"],
                pending,
            )
            return {"response": response}

        pix_request = state["pix_request"]
        if pix_request is None:
            raise ValueError("Pix request is required for transaction execution.")
        return {
            "response": self._orchestrator.transaction_execute(
                state["payload"].session_id,
                pix_request,
            )
        }

    def _emergency_node(self, state: WorkflowState) -> WorkflowState:
        return {"response": self._orchestrator.emergency(state["payload"])}
