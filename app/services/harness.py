from __future__ import annotations

import re
import unicodedata

from app.config import settings
from app.graph.workflow import DemoWorkflowGraph
from app.schemas.auth import AuthContext
from app.schemas.harness import HarnessResponse
from app.schemas.messages import ChatRequest
from app.schemas.outbound import PixCreateRequest
from app.security.guardrails import GuardrailsService
from app.security.rbac import RBACService
from app.services.checkpoint_store import CheckpointStore, checkpoint_store
from app.services.intent_router import IntentRouter
from app.services.observability import traceable
from app.services.orchestrator import DemoOrchestrator, PendingPixOperation
from app.services.response_builder import ResponseBuilder
from app.services.trace_store import trace_store


class DemoHarness:
    def __init__(
        self,
        router: IntentRouter | None = None,
        response_builder: ResponseBuilder | None = None,
        rbac_service: RBACService | None = None,
        guardrails_service: GuardrailsService | None = None,
        checkpoints: CheckpointStore | None = None,
    ) -> None:
        self._router = router or IntentRouter()
        self._response_builder = response_builder or ResponseBuilder()
        self._rbac_service = rbac_service or RBACService()
        self._guardrails_service = guardrails_service or GuardrailsService()
        self._orchestrator = DemoOrchestrator(self._response_builder, self._rbac_service)
        self._workflow_graph = DemoWorkflowGraph(self._orchestrator)
        self._checkpoints = checkpoints or checkpoint_store

    def handle_message(self, payload: ChatRequest) -> dict:
        response = self._handle_message(payload)
        response_payload = response.model_dump()
        trace_store.record(payload.session_id, response_payload)
        return response_payload

    @traceable(name="Agent Harness", run_type="chain")
    def _handle_message(self, payload: ChatRequest) -> HarnessResponse:
        self._guardrails_service.validate_message(payload.message)
        if self._is_confirmation_message(payload.message):
            return self._resume_pending_operation(payload)
        route = self._classify_intent(payload.message)
        return self._dispatch(route, payload)

    @traceable(name="Intent Router", run_type="chain")
    def _classify_intent(self, message: str) -> str:
        return self._router.classify(message)

    def _dispatch(self, route: str, payload: ChatRequest) -> HarnessResponse:
        auth = AuthContext(customer_id=payload.customer_id, role=payload.role)

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

        return self._workflow_graph.invoke(payload, auth, route)

    def _resume_pending_operation(self, payload: ChatRequest) -> HarnessResponse:
        pending = self._checkpoints.get_pending_pix(payload.session_id)
        if pending is None:
            raise ValueError("Nao existe operacao pendente para confirmacao nesta sessao.")

        response = self._workflow_graph.invoke(
            payload,
            AuthContext(customer_id=payload.customer_id, role=payload.role),
            "transaction",
            pending_operation=pending,
        )
        self._checkpoints.consume_pending_pix(payload.session_id)
        return response

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
        if self._contains_sensitive_credential(payload.message):
            return self._response_builder.transaction_blocked_by_policy(
                payload.session_id,
                (
                    "Por seguranca, nao envie senha, iToken, CVV ou dados completos de cartao nesta conversa. "
                    "Para PIX, a confirmacao deve acontecer nos canais oficiais do banco."
                ),
                details,
            )
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

    def _contains_sensitive_credential(self, message: str) -> bool:
        normalized = self._normalize(message)
        sensitive_patterns = [
            r"\bsenha\b",
            r"\bitoken\b",
            r"\bcvv\b",
            r"\bcodigo de seguranca\b",
            r"\bnumero do cartao\b",
            r"\bvalidade do cartao\b",
        ]
        return any(re.search(pattern, normalized) for pattern in sensitive_patterns)

    def _is_suspicious_pix_key(self, destination_key: str, message: str) -> bool:
        normalized_key = self._normalize(destination_key)
        normalized_message = self._normalize(message)
        suspicious_terms = {"suspeita", "fraude", "golpe", "laranja", "desconhecido"}
        return any(term in normalized_key or term in normalized_message for term in suspicious_terms)

    def _is_confirmation_message(self, message: str) -> bool:
        normalized = message.lower().strip()
        return normalized in {"confirmo", "confirmar", "sim, confirmo", "pode confirmar"}
