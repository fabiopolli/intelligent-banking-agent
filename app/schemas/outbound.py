from pydantic import BaseModel, Field


class CustomerProfileResponse(BaseModel):
    customer_id: str
    name: str
    segment: str
    card_status: str
    card_limit: float
    available_limit: float
    credit_score: int = Field(ge=0, le=1000)


class BalanceResponse(BaseModel):
    customer_id: str
    balance: float


class CardLimitUpdateRequest(BaseModel):
    customer_id: str
    new_limit: float = Field(gt=0)


class PixCreateRequest(BaseModel):
    customer_id: str
    amount: float = Field(gt=0)
    destination_key: str = Field(min_length=1)


class AuditEventResponse(BaseModel):
    event_id: str
    idempotency_key: str | None = None
    actor_id: str | None = None
    actor_role: str | None = None
    customer_id: str
    session_id: str | None = None
    trace_id: str | None = None
    event_type: str
    status: str = "executed"
    reason: str | None = None
    timestamp: str
    payload: dict
    user: str
    action: str
    amount: float | None = None
    previous_hash: str | None = None
    event_hash: str
