from __future__ import annotations

from app.config import settings
from app.schemas.harness import HarnessResponse
from app.schemas.outbound import BalanceResponse, CustomerProfileResponse


class ResponseBuilder:
    @staticmethod
    def _format_brl(value: float) -> str:
        rendered = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {rendered}"

    def social(self, session_id: str, message: str) -> HarnessResponse:
        return HarnessResponse(
            route="social_fast_path",
            session_id=session_id,
            message=message,
            observability={
                "tools_called": ["classify_social_message"],
                "retrieval": {"candidate_count": 0, "sources": [], "approved_context": []},
                "llm": {
                    "provider": "not_called",
                    "model": None,
                    "fallback_used": False,
                    "token_usage": None,
                    "prompt": None,
                },
                "planner": {
                    "provider": "not_called",
                    "fallback_used": False,
                    "fallback_reason": "social_fast_path",
                },
            },
        )

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
                f"Seu limite atual e {self._format_brl(profile.card_limit)}. "
                f"Seu limite disponivel e {self._format_brl(profile.available_limit)}."
            ),
            limit_details={
                "current_limit": profile.card_limit,
                "available_limit": profile.available_limit,
                "segment": profile.segment,
                "card_status": profile.card_status,
                "credit_score": profile.credit_score,
            },
        )

    def limit_needs_details(self, session_id: str, profile: CustomerProfileResponse) -> HarnessResponse:
        return HarnessResponse(
            route="core_banking",
            session_id=session_id,
            message=(
                "Para avaliar aumento de limite, preciso do novo valor desejado. "
                f"Seu limite atual e {self._format_brl(profile.card_limit)}."
            ),
            pending_operation="collect_limit_details",
            limit_details={
                "current_limit": profile.card_limit,
                "available_limit": profile.available_limit,
                "segment": profile.segment,
                "card_status": profile.card_status,
                "credit_score": profile.credit_score,
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
                f"O novo limite de {self._format_brl(requested_limit)} esta elegivel. "
                "Confira o valor e envie 'confirmo' para concluir."
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
                "credit_score": profile.credit_score,
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
                "credit_score": profile.credit_score,
            },
        )

    def limit_update_success(self, session_id: str, card_limit: float, available_limit: float) -> HarnessResponse:
        return HarnessResponse(
            route="core_banking",
            session_id=session_id,
            message=(
                f"Limite atualizado com sucesso para {self._format_brl(card_limit)}. "
                f"Limite disponivel atual: {self._format_brl(available_limit)}."
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
            message=f"Seu saldo atual e {self._format_brl(balance.balance)}.",
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
            message=f"PIX realizado com sucesso. Seu saldo atualizado e {self._format_brl(balance)}.",
            balance=balance,
            pix_details=pix_details or {},
        )

    def operation_cancelled(self, session_id: str, operation: str) -> HarnessResponse:
        is_pix = operation == "create_pix"
        return HarnessResponse(
            route="transaction" if is_pix else "core_banking",
            session_id=session_id,
            message=(
                "Pix não autorizado. Nenhum valor foi transferido."
                if is_pix
                else "Alteração de limite não autorizada. Seu limite atual foi mantido."
            ),
            pending_operation=None,
            requires_confirmation=False,
            observability={
                "hitl": {
                    "status": "cancelled",
                    "events": [{"type": "cancelled"}],
                }
            },
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
