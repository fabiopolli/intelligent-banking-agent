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
            message=(
                f"Seu limite atual e R$ {profile.card_limit:.2f}. "
                f"Seu limite disponivel e R$ {profile.available_limit:.2f}."
            ),
            limit_details={
                "current_limit": profile.card_limit,
                "available_limit": profile.available_limit,
                "segment": profile.segment,
                "card_status": profile.card_status,
            },
        )

    def limit_needs_details(self, session_id: str, profile: CustomerProfileResponse) -> HarnessResponse:
        return HarnessResponse(
            route="core_banking",
            session_id=session_id,
            message=(
                "Para avaliar aumento de limite, preciso do novo valor desejado. "
                f"Seu limite atual e R$ {profile.card_limit:.2f}."
            ),
            pending_operation="collect_limit_details",
            limit_details={
                "current_limit": profile.card_limit,
                "available_limit": profile.available_limit,
                "segment": profile.segment,
                "card_status": profile.card_status,
            },
        )

    def limit_update_checkpoint(
        self,
        session_id: str,
        profile: CustomerProfileResponse,
        requested_limit: float,
    ) -> HarnessResponse:
        return HarnessResponse(
            route="core_banking",
            session_id=session_id,
            message=(
                "Seu perfil foi consultado e o novo limite esta elegivel nesta demo. "
                "Confira o valor antes de enviar confirmo para concluir."
            ),
            requires_confirmation=True,
            pending_operation="update_card_limit",
            limit_details={
                "current_limit": profile.card_limit,
                "available_limit": profile.available_limit,
                "requested_limit": requested_limit,
                "segment": profile.segment,
                "card_status": profile.card_status,
                "eligible": True,
            },
        )

    def limit_update_blocked(
        self,
        session_id: str,
        profile: CustomerProfileResponse,
        requested_limit: float,
        reason: str,
    ) -> HarnessResponse:
        return HarnessResponse(
            route="core_banking",
            session_id=session_id,
            message=reason,
            pending_operation="limit_policy_review",
            limit_details={
                "current_limit": profile.card_limit,
                "available_limit": profile.available_limit,
                "requested_limit": requested_limit,
                "segment": profile.segment,
                "card_status": profile.card_status,
                "eligible": False,
            },
        )

    def limit_update_success(self, session_id: str, card_limit: float, available_limit: float) -> HarnessResponse:
        return HarnessResponse(
            route="core_banking",
            session_id=session_id,
            message=(
                f"Limite atualizado com sucesso para R$ {card_limit:.2f}. "
                f"Limite disponivel atual: R$ {available_limit:.2f}."
            ),
            limit_details={
                "current_limit": card_limit,
                "available_limit": available_limit,
            },
        )

    def balance(self, session_id: str, balance: BalanceResponse) -> HarnessResponse:
        return HarnessResponse(
            route="core_banking",
            session_id=session_id,
            message=f"Seu saldo atual e R$ {balance.balance:.2f}.",
        )

    def transaction_needs_details(
        self,
        session_id: str,
        missing_fields: list[str],
        pix_details: dict,
    ) -> HarnessResponse:
        readable_missing = " e ".join(missing_fields)
        return HarnessResponse(
            route="transaction",
            session_id=session_id,
            message=(
                "Para seguir com o PIX, preciso confirmar "
                f"{readable_missing}. Envie os dados restantes nesta conversa."
            ),
            pending_operation="collect_pix_details",
            pix_details=pix_details,
        )

    def transaction_checkpoint(self, session_id: str, pix_details: dict | None = None) -> HarnessResponse:
        return HarnessResponse(
            route="transaction",
            session_id=session_id,
            message=(
                "Fluxo de PIX identificado. Confirmacao formal sera necessaria antes da execucao. "
                "Confira valor e chave antes de enviar confirmo."
            ),
            hitl_threshold=settings.hitl_pix_threshold,
            requires_confirmation=True,
            pending_operation="create_pix",
            pix_details=pix_details or {},
        )

    def transaction_blocked_by_policy(
        self,
        session_id: str,
        message: str,
        pix_details: dict | None = None,
    ) -> HarnessResponse:
        return HarnessResponse(
            route="transaction",
            session_id=session_id,
            message=message,
            pending_operation="pix_policy_review",
            pix_details=pix_details or {},
        )

    def transaction_success(self, session_id: str, balance: float, pix_details: dict | None = None) -> HarnessResponse:
        return HarnessResponse(
            route="transaction",
            session_id=session_id,
            message=f"PIX realizado com sucesso. Seu saldo atualizado e R$ {balance:.2f}.",
            balance=balance,
            pix_details=pix_details or {},
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
