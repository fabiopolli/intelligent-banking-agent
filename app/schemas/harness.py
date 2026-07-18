from pydantic import BaseModel


class HarnessResponse(BaseModel):
    route: str
    session_id: str
    message: str
    card_status: str | None = None
    hitl_threshold: float | None = None
