from __future__ import annotations

from typing import Literal, TypedDict

from app.schemas.auth import AuthContext
from app.schemas.harness import HarnessResponse
from app.schemas.messages import ChatRequest
from app.schemas.outbound import PixCreateRequest


WorkflowRoute = Literal[
    "faq_fast_path",
    "core_banking_limit",
    "core_banking_balance",
    "transaction",
    "emergency",
]

WorkflowNode = Literal[
    "faq_node",
    "core_banking_limit_node",
    "core_banking_balance_node",
    "transaction_node",
    "emergency_node",
]


class WorkflowState(TypedDict):
    payload: ChatRequest
    auth: AuthContext
    route: WorkflowRoute
    next_node: WorkflowNode
    response: HarnessResponse | None
    pix_request: PixCreateRequest | None
    pending_operation: dict[str, str | float] | None
