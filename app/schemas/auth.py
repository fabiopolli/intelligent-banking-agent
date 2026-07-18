from typing import Literal

from pydantic import BaseModel


UserRole = Literal["customer", "manager", "admin"]


class AuthContext(BaseModel):
    customer_id: str
    role: UserRole = "customer"
