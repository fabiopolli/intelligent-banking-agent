from __future__ import annotations

from app.schemas.auth import AuthContext


class RBACService:
    def validate_owner_access(self, auth: AuthContext, target_customer_id: str) -> None:
        if auth.role in {"manager", "admin"}:
            return
        if auth.customer_id != target_customer_id:
            raise PermissionError("Acesso Indevido: Tentativa de violacao de IDOR/BOLA detectada pelo Harness.")
