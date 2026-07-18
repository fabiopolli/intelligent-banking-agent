from pydantic import BaseModel, Field


class CustomerProfileResponse(BaseModel):
    customer_id: str
    name: str
    segment: str
    card_status: str
    card_limit: float
    available_limit: float


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
