from fastapi import APIRouter, Depends, HTTPException

from app.schemas.outbound import (
    AuditEventResponse,
    BalanceResponse,
    CardLimitUpdateRequest,
    CardUnlockRequest,
    CustomerProfileResponse,
    PixCreateRequest,
)
from app.security.internal_tools import require_internal_tool_key
from app.services.mock_bank import mock_bank_service
from app.services.mcp_registry import mcp_tool_registry
from app.services.observability import langsmith_status
from app.services.knowledge_base import knowledge_service
from app.services.trace_store import trace_store
from app.services.audit_log import audit_log_service

router = APIRouter(tags=["outbound-mocks"], dependencies=[Depends(require_internal_tool_key)])


@router.get("/mcp/tools")
def list_mcp_tools() -> dict:
    return {"tools": mcp_tool_registry.list_tools()}


@router.get("/mcp/resources")
def list_mcp_resources() -> dict:
    return {"resources": mcp_tool_registry.list_resources()}


@router.get("/mcp/users/profile/{customer_id}", response_model=CustomerProfileResponse)
def get_customer_profile(customer_id: str) -> CustomerProfileResponse:
    profile = mock_bank_service.get_customer_profile(customer_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return profile


@router.get("/mcp/accounts/balance/{customer_id}", response_model=BalanceResponse)
def get_account_balance(customer_id: str) -> BalanceResponse:
    balance = mock_bank_service.get_balance(customer_id)
    if balance is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return balance


@router.post("/mcp/cards/limit")
def update_card_limit(payload: CardLimitUpdateRequest) -> dict:
    return mock_bank_service.update_card_limit(payload)


@router.post("/mcp/cards/unlock")
def unlock_card(payload: CardUnlockRequest) -> dict:
    return mock_bank_service.unlock_card(payload.customer_id)


@router.post("/mcp/payments/pix")
def create_pix(payload: PixCreateRequest) -> dict:
    return mock_bank_service.create_pix(payload)


@router.get("/mcp/audit/{customer_id}", response_model=list[AuditEventResponse])
def get_audit_events(customer_id: str) -> list[AuditEventResponse]:
    return mock_bank_service.get_audit_events(customer_id)


@router.get("/mcp/audit-integrity")
def get_audit_integrity() -> dict:
    return audit_log_service.verify_integrity()


@router.get("/mcp/trace/{session_id}")
def get_last_trace(session_id: str) -> dict:
    trace = trace_store.get(session_id)
    return {
        "session_id": session_id,
        "trace": trace,
        "history": trace_store.history(session_id),
        "hitl": trace_store.hitl_summary(session_id),
    }


@router.get("/mcp/observability/status")
def get_observability_status() -> dict:
    return {"langsmith": langsmith_status()}


@router.get("/mcp/knowledge/status")
def get_knowledge_status() -> dict:
    return knowledge_service.status()
