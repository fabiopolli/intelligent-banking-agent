from fastapi import APIRouter, HTTPException

from app.schemas.messages import ChatRequest
from app.services.harness import DemoHarness

router = APIRouter(tags=["inbound"])
harness = DemoHarness()


@router.post("/channels/app/chat")
def app_chat(payload: ChatRequest) -> dict:
    try:
        return harness.handle_message(payload)
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
