from fastapi.testclient import TestClient

from app.main import app
from app.api.inbound import harness
from app.schemas.messages import ChatRequest
from app.services.harness import DemoHarness
from app.services.mock_bank import mock_bank_service


client = TestClient(app)


def test_chat_balance_smoke() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={"session_id": "sess-1", "customer_id": "123", "message": "Qual meu saldo?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "core_banking"
    assert "saldo" in body["message"].lower()


def test_stateful_limit_update_smoke() -> None:
    update_response = client.post(
        "/v1/mcp/cards/limit",
        json={"customer_id": "123", "new_limit": 15000},
    )
    assert update_response.status_code == 200
    assert update_response.json()["card_limit"] == 15000

    profile_response = client.get("/v1/mcp/users/profile/123")
    assert profile_response.status_code == 200
    assert profile_response.json()["card_limit"] == 15000

    audit_response = client.get("/v1/mcp/audit/123")
    assert audit_response.status_code == 200
    audit_body = audit_response.json()
    assert audit_body[-1]["event_type"] == "LIMIT_CHANGE"


def test_empty_message_is_rejected() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={"session_id": "sess-2", "customer_id": "123", "message": "   "},
    )
    assert response.status_code == 400


def test_pix_requires_confirmation_and_updates_balance_after_resume() -> None:
    checkpoint_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-3",
            "customer_id": "123",
            "message": "Quero fazer um pix de 7000 para a minha chave",
        },
    )
    assert checkpoint_response.status_code == 200
    checkpoint_body = checkpoint_response.json()
    assert checkpoint_body["route"] == "transaction"
    assert checkpoint_body["requires_confirmation"] is True
    assert checkpoint_body["pending_operation"] == "create_pix"

    resume_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-3",
            "customer_id": "123",
            "message": "confirmo",
        },
    )
    assert resume_response.status_code == 200
    resume_body = resume_response.json()
    assert resume_body["route"] == "transaction"
    assert resume_body["balance"] == 18000.0


def test_emergency_flow_blocks_card() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={"session_id": "sess-4", "customer_id": "123", "message": "Fui roubado"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "emergency"
    assert body["card_status"] == "BLOCKED"
    history = mock_bank_service.get_service_history("123")
    assert history[-1]["action"] == "CARD_BLOCKED"
    audit_response = client.get("/v1/mcp/audit/123")
    assert audit_response.status_code == 200
    assert audit_response.json()[-1]["event_type"] == "CARD_BLOCKED"


def test_low_value_pix_executes_without_confirmation() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-5",
            "customer_id": "123",
            "message": "Quero fazer um pix de 100 para a minha chave",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "transaction"
    assert body["requires_confirmation"] is False
    assert body["balance"] == 24900.0


def test_confirmation_cannot_be_reused_after_pending_operation_is_consumed() -> None:
    client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-6",
            "customer_id": "123",
            "message": "Quero fazer um pix de 7000 para a minha chave",
        },
    )

    first_confirmation = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-6",
            "customer_id": "123",
            "message": "confirmo",
        },
    )
    assert first_confirmation.status_code == 200

    second_confirmation = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-6",
            "customer_id": "123",
            "message": "confirmo",
        },
    )
    assert second_confirmation.status_code == 400


def test_pending_pix_checkpoint_survives_harness_recreation() -> None:
    first_harness = DemoHarness()
    checkpoint = first_harness.handle_message(
        ChatRequest(
            session_id="sess-persisted",
            customer_id="123",
            message="Quero fazer um pix de 7000 para a minha chave",
        )
    )
    assert checkpoint["requires_confirmation"] is True

    recreated_harness = DemoHarness()
    resumed = recreated_harness.handle_message(
        ChatRequest(
            session_id="sess-persisted",
            customer_id="123",
            message="confirmo",
        )
    )

    assert resumed["route"] == "transaction"
    assert resumed["balance"] == 18000.0


def test_workflow_graph_object_is_available_in_harness() -> None:
    assert harness._workflow_graph is not None


def test_pix_emits_append_only_audit_event() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-7",
            "customer_id": "123",
            "message": "Quero fazer um pix de 100 para a minha chave",
        },
    )
    assert response.status_code == 200

    audit_response = client.get("/v1/mcp/audit/123")
    assert audit_response.status_code == 200
    audit_body = audit_response.json()
    assert audit_body[-1]["event_type"] == "PIX"
    assert audit_body[-1]["payload"]["amount"] == 100.0
