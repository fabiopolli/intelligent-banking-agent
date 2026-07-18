from pydantic import BaseModel, Field

from app.schemas.auth import UserRole


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    role: UserRole = "customer"
