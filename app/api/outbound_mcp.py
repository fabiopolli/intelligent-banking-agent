from fastapi import APIRouter, HTTPException

from app.schemas.outbound import (
    AuditEventResponse,
    BalanceResponse,
    CardLimitUpdateRequest,
    CustomerProfileResponse,
    PixCreateRequest,
)
from app.services.mock_bank import mock_bank_service
from app.services.observability import langsmith_status
from app.services.trace_store import trace_store

router = APIRouter(tags=["outbound-mocks"])


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


@router.post("/mcp/payments/pix")
def create_pix(payload: PixCreateRequest) -> dict:
    return mock_bank_service.create_pix(payload)


@router.get("/mcp/audit/{customer_id}", response_model=list[AuditEventResponse])
def get_audit_events(customer_id: str) -> list[AuditEventResponse]:
    return mock_bank_service.get_audit_events(customer_id)


@router.get("/mcp/trace/{session_id}")
def get_last_trace(session_id: str) -> dict:
    trace = trace_store.get(session_id)
    if trace is None:
        return {"session_id": session_id, "trace": None}
    return {"session_id": session_id, "trace": trace}


@router.get("/mcp/observability/status")
def get_observability_status() -> dict:
    return {"langsmith": langsmith_status()}
