from __future__ import annotations

import re
import unicodedata

from app.config import settings
from app.services.agent_planner import Planner, build_agent_planner
from app.graph.workflow import DemoWorkflowGraph
from app.schemas.auth import AuthContext
from app.schemas.harness import HarnessResponse
from app.schemas.messages import ChatRequest
from app.schemas.outbound import PixCreateRequest
from app.security.guardrails import GuardrailsService
from app.security.rbac import RBACService
from app.services.checkpoint_store import CheckpointStore, checkpoint_store
from app.services.observability import traceable
from app.services.customer_support import CustomerSupportService
from app.services.mock_bank import mock_bank_service
from app.services.orchestrator import DemoOrchestrator, PendingLimitOperation, PendingPixOperation
from app.services.response_builder import ResponseBuilder
from app.services.trace_store import trace_store


class DemoHarness:
    def __init__(
        self,
        router: Planner | None = None,
        response_builder: ResponseBuilder | None = None,
        rbac_service: RBACService | None = None,
        guardrails_service: GuardrailsService | None = None,
        checkpoints: CheckpointStore | None = None,
    ) -> None:
        self._router = router or build_agent_planner()
        self._response_builder = response_builder or ResponseBuilder()
        self._rbac_service = rbac_service or RBACService()
        self._guardrails_service = guardrails_service or GuardrailsService()
        self._orchestrator = DemoOrchestrator(self._response_builder, self._rbac_service)
        self._workflow_graph = DemoWorkflowGraph(self._orchestrator)
        self._checkpoints = checkpoints or checkpoint_store

    def handle_message(self, payload: ChatRequest, auth: AuthContext | None = None) -> dict:
        trusted_auth = auth or AuthContext(customer_id=payload.customer_id, role=payload.role)
        response = self._handle_message(payload, trusted_auth)
        response_payload = response.model_dump()
        trace_store.record(payload.session_id, response_payload)
        return response_payload

    @traceable(name="Agent Harness", run_type="chain")
    def _handle_message(self, payload: ChatRequest, auth: AuthContext) -> HarnessResponse:
        self._guardrails_service.validate_message(payload.message)
        if self._guardrails_service.contains_sensitive_credential(payload.message):
            response = self._response_builder.transaction_blocked_by_policy(
                payload.session_id,
                (
                    "Por seguranca, nao envie senha, iToken, CVV ou dados completos de cartao nesta conversa. "
                    "Use somente os canais oficiais do banco para dados de autenticacao."
                ),
            )
            response.observability = {
                "guardrails": {
                    "stage": "pre_llm_ingress",
                    "blocked": True,
                    "reason": "sensitive_credential",
                },
                "planner": {
                    "provider": "not_called",
                    "fallback_used": False,
                    "fallback_reason": "blocked_by_pre_llm_guardrail",
                },
            }
            return response
        if self._is_confirmation_message(payload.message):
            return self._resume_pending_operation(payload, auth)
        if self._has_collectable_limit_draft(payload):
            return self._dispatch("core_banking_limit", payload, auth)
        enriched_payload = self._enrich_documental_followup(payload)
        planner_message = self._guardrails_service.redact_for_llm(enriched_payload.message)
        route = self._classify_intent(planner_message)
        response = self._dispatch(route, enriched_payload, auth)
        planner_trace = getattr(self._router, "last_trace", {}) or {}
        response.observability = {**response.observability, "planner": planner_trace}
        if route == "faq_fast_path" and response.grounding_sources:
            self._checkpoints.save_documental_draft(
                payload.session_id,
                {"last_query": enriched_payload.message},
            )
        return response

    @traceable(name="Intent Router", run_type="chain")
    def _classify_intent(self, message: str) -> str:
        return self._router.classify(message)

    def _dispatch(self, route: str, payload: ChatRequest, auth: AuthContext) -> HarnessResponse:
        self._rbac_service.validate_owner_access(auth, payload.customer_id)
        if route == "transaction":
            pix_request = self._build_pix_request(payload)
            if pix_request is None:
                draft = self._merge_pix_draft(payload)
                missing = self._missing_pix_fields(draft)
                self._checkpoints.save_pix_draft(payload.session_id, draft)
                return self._response_builder.transaction_needs_details(
                    payload.session_id,
                    missing,
                    draft,
                )
            self._checkpoints.consume_pix_draft(payload.session_id)
            policy_response = self._validate_pix_policy(payload, pix_request)
            if policy_response is not None:
                return policy_response
            if pix_request.amount >= settings.hitl_pix_threshold:
                self._checkpoints.save_pending_pix(
                    payload.session_id,
                    PendingPixOperation(
                        customer_id=payload.customer_id,
                        amount=pix_request.amount,
                        destination_key=pix_request.destination_key,
                    ),
                )
                return self._workflow_graph.checkpoint(payload.session_id, pix_request)
            return self._workflow_graph.invoke(payload, auth, route, pix_request=pix_request)

        if route == "core_banking_limit" and (
            self._is_limit_increase_request(payload.message)
            or self._checkpoints.get_limit_draft(payload.session_id) is not None
        ):
            return self._handle_limit_increase(payload, auth)

        return self._workflow_graph.invoke(payload, auth, route)

    def _resume_pending_operation(self, payload: ChatRequest, auth: AuthContext) -> HarnessResponse:
        pending = self._checkpoints.get_pending_pix(payload.session_id)
        if pending is not None:
            response = self._workflow_graph.invoke(
                payload,
                auth,
                "transaction",
                pending_operation=pending,
            )
            self._checkpoints.consume_pending_pix(payload.session_id)
            return response

        pending_limit = self._checkpoints.get_pending_limit(payload.session_id)
        if pending_limit is None:
            raise ValueError("Nao existe operacao pendente para confirmacao nesta sessao.")

        self._rbac_service.validate_owner_access(
            auth,
            pending_limit.customer_id,
        )
        response = self._orchestrator.limit_update_execute(payload.session_id, pending_limit)
        self._checkpoints.consume_pending_limit(payload.session_id)
        return response

    def _handle_limit_increase(self, payload: ChatRequest, auth: AuthContext) -> HarnessResponse:
        self._rbac_service.validate_owner_access(auth, payload.customer_id)
        profile = CustomerSupportService.require_profile(mock_bank_service.get_customer_profile(payload.customer_id))
        requested_limit = self._extract_amount(payload.message)
        if requested_limit is None:
            self._checkpoints.save_limit_draft(payload.session_id, {"customer_id": payload.customer_id})
            return self._response_builder.limit_needs_details(payload.session_id, profile)
        self._checkpoints.consume_limit_draft(payload.session_id)
        if profile.card_status != "ACTIVE":
            return self._response_builder.limit_update_blocked(
                payload.session_id,
                profile,
                requested_limit,
                "Nao posso aumentar limite de um cartao que nao esta ativo.",
            )
        if requested_limit <= profile.card_limit:
            return self._response_builder.limit_update_blocked(
                payload.session_id,
                profile,
                requested_limit,
                "O novo limite precisa ser maior que o limite atual para seguir com a solicitacao.",
            )
        if requested_limit > settings.card_limit_max_eligible:
            return self._response_builder.limit_update_blocked(
                payload.session_id,
                profile,
                requested_limit,
                (
                    f"O valor solicitado excede a politica simulada de elegibilidade de R$ "
                    f"{settings.card_limit_max_eligible:.2f}."
                ),
            )
        self._checkpoints.save_pending_limit(
            payload.session_id,
            PendingLimitOperation(customer_id=payload.customer_id, requested_limit=requested_limit),
        )
        return self._response_builder.limit_update_checkpoint(payload.session_id, profile, requested_limit)

    def _has_collectable_limit_draft(self, payload: ChatRequest) -> bool:
        return (
            self._checkpoints.get_limit_draft(payload.session_id) is not None
            and self._extract_amount(payload.message) is not None
        )

    def _build_pix_request(self, payload: ChatRequest) -> PixCreateRequest | None:
        draft = self._merge_pix_draft(payload)
        missing = self._missing_pix_fields(draft)
        if missing:
            return None
        return PixCreateRequest(
            customer_id=payload.customer_id,
            amount=float(draft["amount"]),
            destination_key=str(draft["destination_key"]),
        )

    def _validate_pix_policy(self, payload: ChatRequest, pix_request: PixCreateRequest) -> HarnessResponse | None:
        details = self._pix_details(pix_request)
        if pix_request.amount > settings.pix_daily_limit:
            return self._response_builder.transaction_blocked_by_policy(
                payload.session_id,
                (
                    f"O valor informado excede o limite diario simulado de PIX de R$ {settings.pix_daily_limit:.2f}. "
                    "Ajuste o valor ou altere o limite nos canais oficiais antes de tentar novamente."
                ),
                details,
            )
        if self._is_suspicious_pix_key(pix_request.destination_key, payload.message):
            return self._response_builder.transaction_blocked_by_policy(
                payload.session_id,
                (
                    "Alerta de Pix suspeito: esta chave ou atividade parece incomum. "
                    "Nao vou executar a transacao nesta demo; confira o destinatario pelos canais oficiais."
                ),
                details,
            )
        return None

    def _merge_pix_draft(self, payload: ChatRequest) -> dict[str, str | float]:
        draft = self._checkpoints.get_pix_draft(payload.session_id) or {}
        amount = self._extract_amount(payload.message)
        destination_key = self._extract_destination_key(payload.message)
        recipient_name = self._extract_recipient_name(payload.message)
        if amount is not None:
            draft["amount"] = amount
        if destination_key is not None:
            draft["destination_key"] = destination_key
        if recipient_name is not None:
            draft["recipient_name"] = recipient_name
        return draft

    def _missing_pix_fields(self, draft: dict[str, str | float]) -> list[str]:
        missing = []
        if "amount" not in draft:
            missing.append("o valor")
        if "destination_key" not in draft:
            missing.append("a chave Pix de destino")
        return missing

    def _extract_amount(self, message: str) -> float | None:
        normalized = message.lower().replace("r$", "").replace(" ", "")
        match = re.search(r"(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?|\d+(?:\.\d+)?)", normalized)
        if match is None:
            return None
        raw_amount = match.group(1)
        if "," in raw_amount:
            raw_amount = raw_amount.replace(".", "").replace(",", ".")
        elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw_amount):
            raw_amount = raw_amount.replace(".", "")
        return float(raw_amount)

    def _extract_destination_key(self, message: str) -> str | None:
        normalized = self._normalize(message)
        key_patterns = [
            r"(?:chave pix|chave|pix para)\s+([a-z0-9_.@+\-]{3,})",
            r"([a-z0-9_.+\-]+@[a-z0-9_.\-]+\.[a-z]{2,})",
            r"(\+?\d{10,14})",
        ]
        for pattern in key_patterns:
            match = re.search(pattern, normalized)
            if match is None:
                continue
            candidate = match.group(1).strip(" .,!?:;")
            if candidate not in {"minha", "minhachave", "chave", "pix"}:
                return candidate
        return None

    def _extract_recipient_name(self, message: str) -> str | None:
        normalized = self._normalize(message)
        match = re.search(r"(?:para|destinatario)\s+([a-z ]{3,40})(?:\s+chave|\s+r\$|\s+\d|$)", normalized)
        if match is None:
            return None
        candidate = " ".join(match.group(1).split()).strip()
        if candidate in {"a minha chave", "minha chave", "chave pix"}:
            return None
        return candidate

    def _normalize(self, message: str) -> str:
        without_accents = "".join(
            char
            for char in unicodedata.normalize("NFKD", message.lower())
            if not unicodedata.combining(char)
        )
        return without_accents

    def _pix_details(self, pix_request: PixCreateRequest) -> dict:
        return {
            "amount": pix_request.amount,
            "destination_key": pix_request.destination_key,
        }

    def _is_suspicious_pix_key(self, destination_key: str, message: str) -> bool:
        normalized_key = self._normalize(destination_key)
        normalized_message = self._normalize(message)
        suspicious_terms = {"suspeita", "fraude", "golpe", "laranja", "desconhecido"}
        return any(term in normalized_key or term in normalized_message for term in suspicious_terms)

    def _is_limit_increase_request(self, message: str) -> bool:
        normalized = self._normalize(message)
        increase_terms = {"aumentar", "aumento", "elevar", "subir", "alterar"}
        return "limite" in normalized and any(term in normalized for term in increase_terms)

    def _enrich_documental_followup(self, payload: ChatRequest) -> ChatRequest:
        draft = self._checkpoints.get_documental_draft(payload.session_id)
        if draft is None or not self._is_documental_context_followup(payload.message):
            return payload
        last_query = draft.get("last_query", "")
        if not last_query:
            return payload
        return ChatRequest(
            session_id=payload.session_id,
            customer_id=payload.customer_id,
            message=f"{last_query} {payload.message}",
            role=payload.role,
        )

    def _is_documental_context_followup(self, message: str) -> bool:
        normalized = self._normalize(message)
        context_terms = {
            "banco24horas",
            "caixa eletronico",
            "conta corrente",
            "conta poupanca",
            "pacote contratado",
            "pacote essencial",
            "poupanca",
            "terminal itau",
            "uso avulso",
        }
        return len(normalized.split()) <= 4 and any(term in normalized for term in context_terms)

    def _is_confirmation_message(self, message: str) -> bool:
        normalized = message.lower().strip()
        return normalized in {"confirmo", "confirmar", "sim, confirmo", "pode confirmar"}
