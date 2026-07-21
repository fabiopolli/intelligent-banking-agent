from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.schemas.auth import AuthContext


@dataclass(frozen=True)
class DemoPrincipal:
    principal_id: str
    role: str
    customer_id: str | None = None
    scopes: tuple[str, ...] = ()


class DemoIdentityService:
    def resolve_principal(self, token: str | None) -> AuthContext:
        if not settings.demo_auth_required:
            return AuthContext(
                principal_id="local-demo-customer",
                customer_id="123",
                role="customer",
                scopes=("customer:self",),
            )

        principals = {
            settings.demo_customer_token: DemoPrincipal(
                "customer-123", "customer", "123", ("customer:self",)
            ),
            settings.demo_manager_token: DemoPrincipal(
                "manager-demo", "manager", scopes=("customer:any:read",)
            ),
            settings.demo_admin_token: DemoPrincipal(
                "admin-demo",
                "admin",
                scopes=("customer:any:read", "customer:any:write"),
            ),
        }
        principal = principals.get(token or "")
        if principal is None:
            raise PermissionError("Credencial de demonstracao ausente ou invalida.")
        return AuthContext(
            principal_id=principal.principal_id,
            customer_id=principal.customer_id,
            role=principal.role,
            scopes=principal.scopes,
        )

    def authenticate(self, token: str | None, target_customer_id: str) -> AuthContext:
        if not settings.demo_auth_required:
            return AuthContext(
                principal_id=f"local-demo-customer-{target_customer_id}",
                customer_id=target_customer_id,
                role="customer",
                scopes=("customer:self",),
            )
        principal = self.resolve_principal(token)
        if principal.role == "customer" and principal.customer_id != target_customer_id:
            raise PermissionError("Acesso Indevido: cliente nao autorizado para o recurso solicitado.")
        return principal


identity_service = DemoIdentityService()
