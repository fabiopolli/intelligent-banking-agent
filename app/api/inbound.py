from fastapi import APIRouter, Header, HTTPException

from app.schemas.messages import ChatRequest
from app.services.harness import DemoHarness
from app.security.identity import identity_service

router = APIRouter(tags=["inbound"])
harness = DemoHarness()


@router.post("/channels/app/chat")
def app_chat(payload: ChatRequest, x_demo_auth_token: str | None = Header(default=None)) -> dict:
    try:
        principal = identity_service.authenticate(x_demo_auth_token, payload.customer_id)
        trusted_payload = payload.model_copy(update={"role": principal.role})
        return harness.handle_message(trusted_payload, auth=principal)
    except PermissionError as exc:
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
