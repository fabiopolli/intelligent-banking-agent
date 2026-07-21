from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.schemas.auth import AuthContext


@dataclass(frozen=True)
class DemoPrincipal:
    principal_id: str
    role: str
    customer_id: str | None = None


class DemoIdentityService:
    def authenticate(self, token: str | None, target_customer_id: str) -> AuthContext:
        if not settings.demo_auth_required:
            return AuthContext(customer_id=target_customer_id, role="customer")

        principals = {
            settings.demo_customer_token: DemoPrincipal("customer-123", "customer", "123"),
            settings.demo_manager_token: DemoPrincipal("manager-demo", "manager"),
            settings.demo_admin_token: DemoPrincipal("admin-demo", "admin"),
        }
        principal = principals.get(token or "")
        if principal is None:
            raise PermissionError("Credencial de demonstracao ausente ou invalida.")
        if principal.role == "customer" and principal.customer_id != target_customer_id:
            raise PermissionError("Acesso Indevido: cliente nao autorizado para o recurso solicitado.")
        return AuthContext(customer_id=principal.customer_id or principal.principal_id, role=principal.role)


identity_service = DemoIdentityService()
