from __future__ import annotations

from app.schemas.auth import AuthContext


class RBACService:
    def validate_owner_access(
        self,
        auth: AuthContext,
        target_customer_id: str,
        access: str = "read",
    ) -> None:
        if auth.role == "customer":
            if auth.customer_id != target_customer_id:
                raise PermissionError("Acesso Indevido: Tentativa de violacao de IDOR/BOLA detectada pelo Harness.")
            return

        required_scope = f"customer:any:{access}"
        if required_scope not in auth.scopes:
            raise PermissionError(
                f"Acesso Indevido: o perfil {auth.role} nao possui o escopo {required_scope}."
            )
