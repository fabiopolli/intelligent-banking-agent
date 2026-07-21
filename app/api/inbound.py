import time

from fastapi import APIRouter, Header, HTTPException

from app.schemas.messages import ChatRequest
from app.services.harness import DemoHarness
from app.security.identity import identity_service
from app.security.guardrails import GuardrailsService
from app.security.target_resolution import target_customer_resolver
from app.services.audit_log import AuditExecutionContext, audit_execution_scope, audit_log_service

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
        return harness.handle_message(
            trusted_payload,
            auth=principal,
            request_started_at=request_started_at,
        )
    except PermissionError as exc:
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/channels/whatsapp/webhook")
def whatsapp_webhook(payload: ChatRequest) -> dict:
    return {
        "accepted": True,
        "session_id": payload.session_id,
        "message": "Webhook accepted for background processing simulation.",
    }
