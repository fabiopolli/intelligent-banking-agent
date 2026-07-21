from typing import Literal

from pydantic import BaseModel


UserRole = Literal["customer", "manager", "admin"]


class AuthContext(BaseModel):
    principal_id: str
    customer_id: str | None = None
    role: UserRole = "customer"
    scopes: tuple[str, ...] = ()
