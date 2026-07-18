from fastapi.testclient import TestClient

from app.main import app


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


def test_empty_message_is_rejected() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={"session_id": "sess-2", "customer_id": "123", "message": "   "},
    )
    assert response.status_code == 400
