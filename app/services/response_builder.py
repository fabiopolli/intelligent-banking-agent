from __future__ import annotations

from app.config import settings
from app.schemas.harness import HarnessResponse
from app.schemas.outbound import BalanceResponse, CustomerProfileResponse


class ResponseBuilder:
    def emergency(self, session_id: str, profile: CustomerProfileResponse) -> HarnessResponse:
        return HarnessResponse(
            route="emergency",
            session_id=session_id,
            message="Seu caso foi priorizado para emergencia. Vamos bloquear o cartao preventivamente.",
            card_status=profile.card_status,
        )

    def limit(self, session_id: str, profile: CustomerProfileResponse) -> HarnessResponse:
        return HarnessResponse(
            route="core_banking",
            session_id=session_id,
            message=f"Seu limite atual e R$ {profile.card_limit:.2f}.",
        )

    def balance(self, session_id: str, balance: BalanceResponse) -> HarnessResponse:
        return HarnessResponse(
            route="core_banking",
            session_id=session_id,
            message=f"Seu saldo atual e R$ {balance.balance:.2f}.",
        )

    def transaction_checkpoint(self, session_id: str) -> HarnessResponse:
        return HarnessResponse(
            route="transaction",
            session_id=session_id,
            message="Fluxo de PIX identificado. Confirmacao formal sera necessaria antes da execucao.",
            hitl_threshold=settings.hitl_pix_threshold,
            requires_confirmation=True,
            pending_operation="create_pix",
        )

    def transaction_success(self, session_id: str, balance: float) -> HarnessResponse:
        return HarnessResponse(
            route="transaction",
            session_id=session_id,
            message=f"PIX realizado com sucesso. Seu saldo atualizado e R$ {balance:.2f}.",
            balance=balance,
        )

    def faq_fast_path(self, session_id: str) -> HarnessResponse:
        return HarnessResponse(
            route="faq_fast_path",
            session_id=session_id,
            message="Entendi sua pergunta. Esta etapa inicial usa um fast path para respostas estaveis e um harness local demonstravel.",
        )

    def grounded_knowledge(
        self,
        session_id: str,
        message: str,
        sources: list[str],
        observability: dict | None = None,
    ) -> HarnessResponse:
        return HarnessResponse(
            route="faq_fast_path",
            session_id=session_id,
            message=message,
            grounding_sources=sources,
            observability=observability or {},
        )
