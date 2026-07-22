import time

from fastapi import APIRouter, Header, HTTPException

from app.schemas.messages import ChatRequest
from app.services.harness import DemoHarness
from app.security.identity import identity_service
from app.security.guardrails import GuardrailsService
from app.security.target_resolution import target_customer_resolver
from app.security.request_credentials import trusted_auth_token_scope
from app.services.audit_log import AuditExecutionContext, audit_execution_scope, audit_log_service
from app.services.internal_systems import InternalSystemsUnavailable
from app.services.trace_store import trace_store

router = APIRouter(tags=["inbound"])
harness = DemoHarness()
ingress_guardrails = GuardrailsService()


@router.get("/auth/demo/session")
def demo_session(x_demo_auth_token: str | None = Header(default=None)) -> dict:
    try:
        return identity_service.resolve_principal(x_demo_auth_token).model_dump()
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/channels/app/chat")
def app_chat(payload: ChatRequest, x_demo_auth_token: str | None = Header(default=None)) -> dict:
    request_started_at = time.perf_counter()
    principal = None
    target_customer_id = payload.customer_id
    try:
        principal = identity_service.resolve_principal(x_demo_auth_token)
        if ingress_guardrails.contains_sensitive_credential(payload.message):
            trusted_payload = payload.model_copy(update={"role": principal.role})
            with trusted_auth_token_scope(x_demo_auth_token):
                return harness.handle_message(
                    trusted_payload,
                    auth=principal,
                    request_started_at=request_started_at,
                )
        target_customer_id = target_customer_resolver.resolve(payload.message, payload.customer_id)
        principal = identity_service.authenticate(x_demo_auth_token, target_customer_id)
        trusted_payload = payload.model_copy(
            update={
                "customer_id": target_customer_id,
                "role": principal.role,
                "message": target_customer_resolver.remove_reference(payload.message),
            }
        )
        with trusted_auth_token_scope(x_demo_auth_token):
            return harness.handle_message(
                trusted_payload,
                auth=principal,
                request_started_at=request_started_at,
            )
    except PermissionError as exc:
        _record_failure(
            payload.session_id,
            request_started_at,
            http_status=403,
            stage="authentication_or_rbac",
            error_code="authorization_denied",
            error_type=type(exc).__name__,
            summary="A identidade não possui autorização para a conta ou operação solicitada.",
            probable_cause="Cliente alvo diferente da identidade ou escopo de escrita ausente.",
            suggested_action="Confira o perfil autenticado e o cliente alvo no chat.",
        )
        if principal is not None:
            with audit_execution_scope(
                AuditExecutionContext(
                    actor_id=principal.principal_id,
                    actor_role=principal.role,
                    customer_id=target_customer_id,
                    session_id=payload.session_id,
                    trace_id=payload.session_id,
                )
            ):
                audit_log_service.append(
                    target_customer_id,
                    "ACCESS_DENIED",
                    {"target_customer_id": target_customer_id},
                    status="blocked",
                    reason=str(exc),
                )
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        _record_failure(
            payload.session_id,
            request_started_at,
            http_status=400,
            stage="request_validation",
            error_code="invalid_request",
            error_type=type(exc).__name__,
            summary="A solicitação não passou pela validação de formato ou política.",
            probable_cause="Campo ausente, valor inválido ou mensagem incompatível com a operação.",
            suggested_action="Revise os dados solicitados e tente novamente na mesma sessão.",
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except InternalSystemsUnavailable as exc:
        _record_failure(
            payload.session_id,
            request_started_at,
            http_status=503,
            stage="mcp_internal_systems",
            error_code="internal_system_unavailable",
            error_type=type(exc).__name__,
            summary="A ferramenta interna não concluiu a solicitação.",
            probable_cause="Timeout, indisponibilidade ou erro de protocolo na integração MCP.",
            suggested_action="Verifique API, servidor MCP e sistema interno; depois repita a operação.",
        )
        raise HTTPException(
            status_code=503,
            detail="Sistema bancario interno temporariamente indisponivel. Tente novamente em instantes.",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        _record_failure(
            payload.session_id,
            request_started_at,
            http_status=500,
            stage="agent_harness",
            error_code="unexpected_error",
            error_type=type(exc).__name__,
            summary="O fluxo foi interrompido por uma falha técnica não prevista.",
            probable_cause="Erro interno no Harness, provider, grafo ou construção da resposta.",
            suggested_action="Consulte os logs da API pelo horário e pelo Session ID desta interação.",
        )
        raise HTTPException(
            status_code=500,
            detail="Nao foi possivel concluir a solicitacao. Tente novamente em instantes.",
        ) from exc


def _record_failure(
    session_id: str,
    request_started_at: float,
    *,
    http_status: int,
    stage: str,
    error_code: str,
    error_type: str,
    summary: str,
    probable_cause: str,
    suggested_action: str,
) -> None:
    duration_ms = round((time.perf_counter() - request_started_at) * 1000)
    trace_store.record(
        session_id,
        {
            "route": "error",
            "session_id": session_id,
            "message": "Interação não concluída.",
            "requires_confirmation": False,
            "grounding_sources": [],
            "observability": {
                "failure": {
                    "status": "failed",
                    "http_status": http_status,
                    "stage": stage,
                    "error_code": error_code,
                    "error_type": error_type,
                    "summary": summary,
                    "probable_cause": probable_cause,
                    "suggested_action": suggested_action,
                    "duration_ms": duration_ms,
                },
                "timings": {"api_total_ms": duration_ms},
            },
        },
    )


@router.post("/channels/whatsapp/webhook")
def whatsapp_webhook(payload: ChatRequest) -> dict:
    return {
        "accepted": True,
        "session_id": payload.session_id,
        "message": "Webhook accepted for background processing simulation.",
    }
