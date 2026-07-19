from pydantic import BaseModel, Field


class HarnessResponse(BaseModel):
    route: str
    session_id: str
    message: str
    card_status: str | None = None
    hitl_threshold: float | None = None
    requires_confirmation: bool = False
    pending_operation: str | None = None
    balance: float | None = None
    grounding_sources: list[str] = Field(default_factory=list)
    observability: dict = Field(default_factory=dict)
