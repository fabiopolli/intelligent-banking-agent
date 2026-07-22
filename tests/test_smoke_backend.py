import asyncio
import os
import socket
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api.inbound import harness
from app.schemas.messages import ChatRequest
from app.config import settings
from app.services.checkpoint_store import CheckpointStore
from app.services.harness import DemoHarness
from app.services.knowledge.llm import (
    DockerModelRunnerGroundedFaqSynthesizer,
    OpenAIGroundedFaqSynthesizer,
    build_grounded_faq_synthesizer,
)
from app.services.knowledge.service import GroundedKnowledgeService
from app.services.mock_bank import mock_bank_service
from app.services.orchestrator import PendingPixOperation
from app.services.audit_log import (
    AuditExecutionContext,
    audit_execution_scope,
    audit_log_service,
)
from app.services.agent_planner import DeterministicPlanner
from app.services.internal_systems import InternalSystemsUnavailable, McpInternalSystemsGateway
from app.security.request_credentials import trusted_auth_token_scope
from app.schemas.outbound import BalanceResponse, CustomerProfileResponse
from scripts.smoke_mcp_client import run_smoke


client = TestClient(app)
INTERNAL_TOOL_HEADERS = {"X-Internal-Tool-Key": settings.internal_tool_api_key}


def _demo_auth_headers(token: str) -> dict[str, str]:
    return {"X-Demo-Auth-Token": token}


class RecordingSynthesizer:
    provider_name = "fake-recording"

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.last_trace = {"provider": self.provider_name, "fallback_used": False}

    def synthesize(self, query, contexts) -> str:  # noqa: ANN001
        self.calls.append((query, [context.source for context in contexts]))
        return "Resposta sintetizada somente com contexto oficial recuperado."


class FallbackRecordingSynthesizer(RecordingSynthesizer):
    provider_name = "fake-fallback-recording"

    def synthesize(self, query, contexts) -> str:  # noqa: ANN001
        self.calls.append((query, [context.source for context in contexts]))
        self.last_trace = {"provider": self.provider_name, "fallback_used": True}
        return "Pagina 23. trecho bruto do PDF que nao deve aparecer."


def test_chat_balance_smoke() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={"session_id": "sess-1", "customer_id": "123", "message": "Qual meu saldo?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "core_banking"
    assert "saldo" in body["message"].lower()
    assert body["observability"]["timings"]["api_total_ms"] >= 0
    assert body["observability"]["timings"]["harness_total_ms"] >= 0
    assert body["observability"]["timings"]["routing_ms"] >= 0

    trace_response = client.get("/v1/mcp/trace/sess-1", headers=INTERNAL_TOOL_HEADERS)
    assert trace_response.status_code == 200
    assert trace_response.json()["trace"]["route"] == "core_banking"


def test_core_banking_read_uses_injected_internal_systems_gateway(monkeypatch) -> None:  # noqa: ANN001
    class RecordingGateway:
        def __init__(self) -> None:
            self.calls = []
            self.last_trace = {}

        def get_customer_profile(self, customer_id: str):  # noqa: ANN201
            self.calls.append(("get_customer_profile", customer_id))
            self.last_trace = {
                "tool": "get_customer_profile",
                "transport": "mcp-streamable-http",
                "status": "success",
                "duration_ms": 2,
            }
            return CustomerProfileResponse(
                customer_id=customer_id,
                name="Gateway Customer",
                segment="Demo",
                card_status="ACTIVE",
                card_limit=1000,
                available_limit=1000,
                credit_score=820,
            )

        def get_account_balance(self, customer_id: str):  # noqa: ANN201
            self.calls.append(("get_account_balance", customer_id))
            self.last_trace = {
                "tool": "get_account_balance",
                "transport": "mcp-streamable-http",
                "status": "success",
                "duration_ms": 3,
            }
            return BalanceResponse(customer_id=customer_id, balance=4321)

        def get_card_limit(self, customer_id: str):  # noqa: ANN201
            self.calls.append(("get_card_limit", customer_id))
            self.last_trace = {
                "tool": "get_card_limit",
                "transport": "mcp-streamable-http",
                "status": "success",
                "duration_ms": 4,
            }
            return CustomerProfileResponse(
                customer_id=customer_id,
                name="Gateway Customer",
                segment="Demo",
                card_status="ACTIVE",
                card_limit=1000,
                available_limit=1000,
                credit_score=820,
            )

        def search_official_knowledge(
            self,
            query: str,
            llm_provider: str = "configured",
        ) -> dict:
            self.calls.append(("search_tariff_knowledge", query, llm_provider))
            self.last_trace = {
                "tool": "search_tariff_knowledge",
                "transport": "mcp-streamable-http",
                "status": "success",
                "duration_ms": 5,
            }
            return {
                "message": "Resposta oficial estruturada.",
                "sources": ["official-source"],
                "observability": {
                    "tools_called": ["hybrid_retrieve"],
                    "llm": {"provider": "disabled"},
                    "timings": {"retrieval_ms": 1},
                },
            }

        def update_card_limit(self, payload):  # noqa: ANN001, ANN201
            self.calls.append(("update_card_limit", payload.customer_id, payload.new_limit))
            self.last_trace = {
                "tool": "update_card_limit",
                "transport": "mcp-streamable-http",
                "status": "success",
                "duration_ms": 6,
            }
            return {
                "customer_id": payload.customer_id,
                "card_limit": payload.new_limit,
                "available_limit": payload.new_limit,
            }

        def create_pix(self, payload):  # noqa: ANN001, ANN201
            self.calls.append(("create_pix", payload.customer_id, payload.amount))
            self.last_trace = {
                "tool": "create_pix",
                "transport": "mcp-streamable-http",
                "status": "success",
                "duration_ms": 7,
            }
            return {
                "customer_id": payload.customer_id,
                "balance": 25000 - payload.amount,
                "status": "SUCCESS",
            }

    gateway = RecordingGateway()
    monkeypatch.setattr(
        mock_bank_service,
        "get_balance",
        lambda customer_id: (_ for _ in ()).throw(AssertionError("direct balance access")),
    )

    result = DemoHarness(
        router=DeterministicPlanner(),
        internal_systems=gateway,
    ).handle_message(
        ChatRequest(session_id="mcp-gateway-read", customer_id="123", message="Qual meu saldo?")
    )

    assert gateway.calls == [("get_account_balance", "123")]
    assert "R$ 4.321,00" in result["message"]
    assert result["observability"]["tools_called"] == [
        "mcp-streamable-http.get_account_balance"
    ]
    assert result["observability"]["mcp"][0]["status"] == "success"

    limit_result = DemoHarness(
        router=DeterministicPlanner(),
        internal_systems=gateway,
    ).handle_message(
        ChatRequest(session_id="mcp-gateway-limit", customer_id="123", message="Qual meu limite?")
    )
    assert gateway.calls[-1] == ("get_card_limit", "123")
    assert limit_result["observability"]["tools_called"] == [
        "mcp-streamable-http.get_card_limit"
    ]

    faq_result = DemoHarness(
        router=DeterministicPlanner(),
        internal_systems=gateway,
    ).handle_message(
        ChatRequest(session_id="mcp-gateway-faq", customer_id="123", message="Qual a tarifa de saque?")
    )
    assert gateway.calls[-1] == (
        "search_tariff_knowledge",
        "Qual a tarifa de saque?",
        "configured",
    )
    assert faq_result["grounding_sources"] == ["official-source"]
    assert faq_result["observability"]["tools_called"] == [
        "hybrid_retrieve",
        "mcp-streamable-http.search_tariff_knowledge",
    ]
    assert faq_result["observability"]["mcp"][0]["status"] == "success"


def test_critical_writes_use_mcp_gateway_only_after_hitl() -> None:
    class RecordingWriteGateway:
        def __init__(self) -> None:
            self.calls: list[tuple] = []
            self.last_trace: dict = {}

        def get_card_limit(self, customer_id: str):  # noqa: ANN201
            self.calls.append(("get_card_limit", customer_id))
            return CustomerProfileResponse(
                customer_id=customer_id,
                name="Gateway Customer",
                segment="Demo",
                card_status="ACTIVE",
                card_limit=5000,
                available_limit=5000,
                credit_score=820,
            )

        def update_card_limit(self, payload):  # noqa: ANN001, ANN201
            self.calls.append(("update_card_limit", payload.customer_id, payload.new_limit))
            self.last_trace = {
                "tool": "update_card_limit",
                "transport": "mcp-streamable-http",
                "status": "success",
                "duration_ms": 4,
            }
            return {"card_limit": payload.new_limit, "available_limit": payload.new_limit}

        def create_pix(self, payload):  # noqa: ANN001, ANN201
            self.calls.append(("create_pix", payload.customer_id, payload.amount))
            self.last_trace = {
                "tool": "create_pix",
                "transport": "mcp-streamable-http",
                "status": "success",
                "duration_ms": 5,
            }
            return {"balance": 25000 - payload.amount, "status": "SUCCESS"}

    gateway = RecordingWriteGateway()
    test_harness = DemoHarness(router=DeterministicPlanner(), internal_systems=gateway)

    limit_checkpoint = test_harness.handle_message(
        ChatRequest(
            session_id="mcp-limit-write",
            customer_id="123",
            message="Aumente meu limite para R$ 10.000",
        )
    )
    assert limit_checkpoint["requires_confirmation"] is True
    assert gateway.calls == [("get_card_limit", "123")]

    limit_result = test_harness.handle_message(
        ChatRequest(session_id="mcp-limit-write", customer_id="123", message="confirmo")
    )
    assert gateway.calls[-1] == ("update_card_limit", "123", 10000.0)
    assert limit_result["observability"]["mcp"][0]["tool"] == "update_card_limit"

    pix_checkpoint = test_harness.handle_message(
        ChatRequest(
            session_id="mcp-pix-write",
            customer_id="123",
            message="Faça um Pix de R$ 6.000 para a chave qa@example.com",
        )
    )
    assert pix_checkpoint["requires_confirmation"] is True
    assert not any(call[0] == "create_pix" for call in gateway.calls)

    pix_result = test_harness.handle_message(
        ChatRequest(session_id="mcp-pix-write", customer_id="123", message="confirmo")
    )
    assert gateway.calls[-1] == ("create_pix", "123", 6000.0)
    assert pix_result["observability"]["mcp"][0]["tool"] == "create_pix"


def test_mcp_gateway_failure_is_controlled_and_does_not_trace_credentials(monkeypatch) -> None:  # noqa: ANN001
    gateway = McpInternalSystemsGateway("http://mcp.invalid/mcp")

    async def fail(tool, arguments):  # noqa: ANN001, ANN202
        raise TimeoutError("MCP unavailable")

    monkeypatch.setattr(gateway, "_call_tool_async", fail)
    with trusted_auth_token_scope("secret-demo-token"):
        with pytest.raises(InternalSystemsUnavailable):
            gateway.get_account_balance("123")

    assert gateway.last_trace["status"] == "failed"
    assert gateway.last_trace["error_type"] == "TimeoutError"
    assert "secret-demo-token" not in str(gateway.last_trace)


def test_demo_login_returns_identity_derived_from_token(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "demo_auth_required", True)

    response = client.get(
        "/v1/auth/demo/session",
        headers=_demo_auth_headers(settings.demo_manager_token),
    )

    assert response.status_code == 200
    assert response.json() == {
        "principal_id": "manager-demo",
        "customer_id": None,
        "role": "manager",
        "scopes": ["customer:any:read"],
    }


def test_demo_login_rejects_unknown_token(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "demo_auth_required", True)

    response = client.get(
        "/v1/auth/demo/session",
        headers=_demo_auth_headers("invalid-demo-token"),
    )

    assert response.status_code == 403
    assert "invalida" in response.json()["detail"].lower()


def test_customer_cannot_spoof_role_or_access_another_customer(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "demo_auth_required", True)

    response = client.post(
        "/v1/channels/app/chat",
        headers=_demo_auth_headers(settings.demo_customer_token),
        json={
            "session_id": "sess-customer-idor",
            "customer_id": "456",
            "role": "admin",
            "message": "Qual o saldo?",
        },
    )

    assert response.status_code == 403
    assert "cliente nao autorizado" in response.json()["detail"].lower()


def test_manager_can_read_natural_language_target_but_cannot_write(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "demo_auth_required", True)
    headers = _demo_auth_headers(settings.demo_manager_token)

    balance_response = client.post(
        "/v1/channels/app/chat",
        headers=headers,
        json={
            "session_id": "sess-manager-read",
            "customer_id": "123",
            "role": "customer",
            "message": "Qual o saldo do cliente 456?",
        },
    )
    pix_response = client.post(
        "/v1/channels/app/chat",
        headers=headers,
        json={
            "session_id": "sess-manager-write",
            "customer_id": "123",
            "message": "Faça um pix de 100 do cliente 456 para chave pix qa@example.com",
        },
    )

    assert balance_response.status_code == 200
    assert "R$ 8.000,00" in balance_response.json()["message"]
    assert pix_response.status_code == 403
    assert "customer:any:write" in pix_response.json()["detail"]
    assert mock_bank_service.get_balance("456").balance == 8000.0


def test_admin_scope_allows_write_for_natural_language_target(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "demo_auth_required", True)

    response = client.post(
        "/v1/channels/app/chat",
        headers=_demo_auth_headers(settings.demo_admin_token),
        json={
            "session_id": "sess-admin-write",
            "customer_id": "123",
            "message": "Faça um pix de 100 do cliente 456 para chave pix admin@example.com",
        },
    )

    assert response.status_code == 200
    assert response.json()["balance"] == 7900.0


def test_sensitive_credential_is_blocked_before_target_resolution(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "demo_auth_required", True)

    response = client.post(
        "/v1/channels/app/chat",
        headers=_demo_auth_headers(settings.demo_customer_token),
        json={
            "session_id": "sess-sensitive-before-target",
            "customer_id": "123",
            "message": "Consulte o cliente 456 usando meu iToken 123456",
        },
    )

    assert response.status_code == 200
    assert response.json()["observability"]["guardrails"]["blocked"] is True
    assert response.json()["observability"]["planner"]["provider"] == "not_called"


def test_internal_mcp_endpoints_require_tool_key() -> None:
    response = client.get("/v1/mcp/users/profile/123")

    assert response.status_code == 403
    assert "Internal tool API key" in response.json()["detail"]


def test_fake_profile_matches_mcp_challenge_contract() -> None:
    fabio = client.get("/v1/mcp/users/profile/123", headers=INTERNAL_TOOL_HEADERS)
    gerardo = client.get("/v1/mcp/users/profile/456", headers=INTERNAL_TOOL_HEADERS)

    assert fabio.status_code == 200
    assert fabio.json()["name"] == "Fabio de Melo"
    assert fabio.json()["credit_score"] == 820
    assert gerardo.status_code == 200
    assert gerardo.json()["name"] == "Gerardo da Silva"
    assert gerardo.json()["credit_score"] == 740


def test_mcp_tool_registry_exposes_banking_tools_and_resources() -> None:
    tools_response = client.get("/v1/mcp/tools", headers=INTERNAL_TOOL_HEADERS)
    resources_response = client.get("/v1/mcp/resources", headers=INTERNAL_TOOL_HEADERS)

    assert tools_response.status_code == 200
    assert resources_response.status_code == 200
    tools = tools_response.json()["tools"]
    resources = resources_response.json()["resources"]
    create_pix = next(tool for tool in tools if tool["name"] == "create_pix")
    assert create_pix["requires_rbac"] is True
    assert create_pix["requires_hitl"] is True
    assert create_pix["audited"] is True
    assert any(resource["uri"] == "itau://knowledge/tariff-pdf" for resource in resources)


def test_stateful_limit_update_smoke() -> None:
    update_response = client.post(
        "/v1/mcp/cards/limit",
        json={"customer_id": "123", "new_limit": 15000},
        headers=INTERNAL_TOOL_HEADERS,
    )
    assert update_response.status_code == 200
    assert update_response.json()["card_limit"] == 15000
    assert update_response.json()["available_limit"] == 15000

    profile_response = client.get("/v1/mcp/users/profile/123", headers=INTERNAL_TOOL_HEADERS)
    assert profile_response.status_code == 200
    assert profile_response.json()["card_limit"] == 15000
    assert profile_response.json()["available_limit"] == 15000

    audit_response = client.get("/v1/mcp/audit/123", headers=INTERNAL_TOOL_HEADERS)
    assert audit_response.status_code == 200
    audit_body = audit_response.json()
    assert audit_body[-1]["event_type"] == "LIMIT_CHANGE"


def test_limit_increase_requires_confirmation_and_updates_after_resume() -> None:
    mock_bank_service.reset()
    checkpoint_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-limit-increase",
            "customer_id": "123",
            "message": "Quero aumentar o limite do meu cartao para R$ 15.000",
        },
    )

    assert checkpoint_response.status_code == 200
    checkpoint_body = checkpoint_response.json()
    assert checkpoint_body["route"] == "core_banking"
    assert checkpoint_body["requires_confirmation"] is True
    assert checkpoint_body["pending_operation"] == "update_card_limit"
    assert checkpoint_body["limit_details"]["current_limit"] == 10000.0
    assert checkpoint_body["limit_details"]["requested_limit"] == 15000.0
    assert checkpoint_body["limit_details"]["eligible"] is True
    assert "nesta demo" not in checkpoint_body["message"].lower()
    assert "R$ 15.000,00" in checkpoint_body["message"]

    resume_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-limit-increase",
            "customer_id": "123",
            "message": "confirmo",
        },
    )

    assert resume_response.status_code == 200
    resume_body = resume_response.json()
    assert resume_body["route"] == "core_banking"
    assert resume_body["requires_confirmation"] is False
    assert resume_body["limit_details"]["current_limit"] == 15000.0
    assert resume_body["limit_details"]["available_limit"] == 15000.0
    assert "R$ 15.000,00" in resume_body["message"]

    profile_response = client.get("/v1/mcp/users/profile/123", headers=INTERNAL_TOOL_HEADERS)
    assert profile_response.status_code == 200
    assert profile_response.json()["card_limit"] == 15000.0
    assert profile_response.json()["available_limit"] == 15000.0

    audit_response = client.get("/v1/mcp/audit/123", headers=INTERNAL_TOOL_HEADERS)
    assert audit_response.status_code == 200
    assert audit_response.json()[-1]["event_type"] == "LIMIT_CHANGE"


def test_limit_query_context_allows_followup_increase_without_repeating_subject() -> None:
    first_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "limit-context-session",
            "customer_id": "456",
            "message": "Qual meu limite?",
        },
    )

    assert first_response.status_code == 200
    assert first_response.json()["route"] == "core_banking"

    second_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "limit-context-session",
            "customer_id": "456",
            "message": "Aumenta para 10 mil",
        },
    )

    assert second_response.status_code == 200
    body = second_response.json()
    assert body["route"] == "core_banking"
    assert body["requires_confirmation"] is True
    assert body["pending_operation"] == "update_card_limit"
    assert body["limit_details"]["requested_limit"] == 10000.0


def test_limit_increase_without_amount_collects_details() -> None:
    mock_bank_service.reset()
    first_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-limit-missing-amount",
            "customer_id": "123",
            "message": "Quero aumentar o limite do meu cartao",
        },
    )

    assert first_response.status_code == 200
    first_body = first_response.json()
    assert first_body["route"] == "core_banking"
    assert first_body["requires_confirmation"] is False
    assert first_body["pending_operation"] == "collect_limit_details"
    assert "novo valor desejado" in first_body["message"].lower()

    second_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-limit-missing-amount",
            "customer_id": "123",
            "message": "R$ 15.000",
        },
    )

    assert second_response.status_code == 200
    second_body = second_response.json()
    assert second_body["requires_confirmation"] is True
    assert second_body["pending_operation"] == "update_card_limit"
    assert second_body["limit_details"]["requested_limit"] == 15000.0


def test_limit_increase_above_policy_is_blocked_before_confirmation() -> None:
    mock_bank_service.reset()
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-limit-above-policy",
            "customer_id": "123",
            "message": "Quero aumentar o limite do meu cartao para R$ 25.000",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "core_banking"
    assert body["requires_confirmation"] is False
    assert body["pending_operation"] == "limit_policy_review"
    assert body["limit_details"]["eligible"] is False


def test_limit_increase_below_credit_policy_is_blocked_before_hitl(monkeypatch) -> None:  # noqa: ANN001
    mock_bank_service.reset()
    monkeypatch.setattr(settings, "card_limit_min_credit_score", 900)

    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-limit-credit-policy",
            "customer_id": "123",
            "message": "Quero aumentar o limite do meu cartao para R$ 15.000",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requires_confirmation"] is False
    assert body["pending_operation"] == "limit_policy_review"
    assert body["limit_details"]["eligible"] is False
    assert body["limit_details"]["credit_score"] == 820
    assert "credit score" not in body["message"].lower()
    assert mock_bank_service.get_customer_profile("123").card_limit == 10000.0


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
            "message": "Quero fazer um pix de 7000 para chave pix maria@example.com",
        },
    )
    assert checkpoint_response.status_code == 200
    checkpoint_body = checkpoint_response.json()
    assert checkpoint_body["route"] == "transaction"
    assert checkpoint_body["requires_confirmation"] is True
    assert checkpoint_body["pending_operation"] == "create_pix"
    assert checkpoint_body["pix_details"]["destination_key"] == "maria@example.com"

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

    trace_response = client.get("/v1/mcp/trace/sess-3", headers=INTERNAL_TOOL_HEADERS)
    assert trace_response.status_code == 200
    trace_payload = trace_response.json()
    assert trace_payload["trace"]["balance"] == 18000.0
    assert len(trace_payload["history"]) == 2
    assert trace_payload["hitl"]["encountered"] is True
    assert trace_payload["hitl"]["status"] == "completed"
    assert trace_payload["hitl"]["created_count"] == 1
    assert trace_payload["hitl"]["resumed_count"] == 1
    assert trace_payload["hitl"]["duration_ms"] >= 0
    assert [event["type"] for event in trace_payload["hitl"]["events"]] == [
        "created",
        "resumed",
        "completed",
    ]
    correlation_ids = {
        event["correlation_id"] for event in trace_payload["hitl"]["events"]
    }
    assert len(correlation_ids) == 1


def test_high_value_pix_with_insufficient_balance_is_rejected_after_confirmation() -> None:
    checkpoint_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-insufficient-balance",
            "customer_id": "123",
            "message": "Quero fazer um pix de 30000 para chave pix maria@example.com",
        },
    )
    assert checkpoint_response.status_code == 200
    assert checkpoint_response.json()["requires_confirmation"] is True

    resume_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-insufficient-balance",
            "customer_id": "123",
            "message": "confirmo",
        },
    )
    assert resume_response.status_code == 400
    assert "Saldo insuficiente" in resume_response.json()["detail"]

    balance_response = client.get("/v1/mcp/accounts/balance/123", headers=INTERNAL_TOOL_HEADERS)
    assert balance_response.status_code == 200
    assert balance_response.json()["balance"] == 25000.0


def test_customer_can_reject_pix_without_executing_transfer() -> None:
    checkpoint_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-pix-rejected",
            "customer_id": "123",
            "message": "Quero fazer um pix de 7000 para chave pix maria@example.com",
        },
    )
    assert checkpoint_response.status_code == 200
    assert checkpoint_response.json()["requires_confirmation"] is True

    rejection_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-pix-rejected",
            "customer_id": "123",
            "message": "não autorizo",
        },
    )

    assert rejection_response.status_code == 200
    body = rejection_response.json()
    assert body["requires_confirmation"] is False
    assert body["pending_operation"] is None
    assert "nenhum valor foi transferido" in body["message"].lower()
    assert mock_bank_service.get_balance("123").balance == 25000.0

    trace = client.get("/v1/mcp/trace/sess-pix-rejected", headers=INTERNAL_TOOL_HEADERS).json()
    assert trace["hitl"]["status"] == "cancelled"
    assert [event["type"] for event in trace["hitl"]["events"]] == ["created", "cancelled"]
    assert audit_log_service.list_by_customer("123")[-1]["status"] == "cancelled"


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
    audit_response = client.get("/v1/mcp/audit/123", headers=INTERNAL_TOOL_HEADERS)
    assert audit_response.status_code == 200
    assert audit_response.json()[-1]["event_type"] == "CARD_BLOCKED"


def test_admin_unlocks_blocked_card_only_after_hitl(tmp_path) -> None:  # noqa: ANN001
    from app.schemas.auth import AuthContext
    from app.services.internal_systems import LocalInternalSystemsGateway

    mock_bank_service.reset()
    mock_bank_service.block_card("123")
    store = CheckpointStore(tmp_path / "unlock-checkpoints.json")
    test_harness = DemoHarness(
        router=DeterministicPlanner(),
        checkpoints=store,
        internal_systems=LocalInternalSystemsGateway(),
    )
    admin = AuthContext(
        principal_id="admin-demo",
        role="admin",
        scopes=("customer:any:read", "customer:any:write"),
    )

    checkpoint = test_harness.handle_message(
        ChatRequest(
            session_id="admin-unlock-card",
            customer_id="123",
            message="Desbloqueie o cartão do cliente 123",
        ),
        auth=admin,
    )
    assert checkpoint["requires_confirmation"] is True
    assert checkpoint["pending_operation"] == "unlock_card"
    assert mock_bank_service.get_customer_profile("123").card_status == "BLOCKED"

    completed = test_harness.handle_message(
        ChatRequest(session_id="admin-unlock-card", customer_id="123", message="confirmo"),
        auth=admin,
    )
    assert completed["card_status"] == "ACTIVE"
    assert completed["observability"]["tools_called"] == ["local-adapter.unlock_card"]


def test_customer_and_manager_cannot_request_card_unlock(tmp_path) -> None:  # noqa: ANN001
    from app.schemas.auth import AuthContext
    from app.services.internal_systems import LocalInternalSystemsGateway

    test_harness = DemoHarness(
        router=DeterministicPlanner(),
        checkpoints=CheckpointStore(tmp_path / "denied-unlock.json"),
        internal_systems=LocalInternalSystemsGateway(),
    )
    identities = [
        AuthContext(principal_id="customer-123", role="customer", customer_id="123", scopes=("customer:self",)),
        AuthContext(principal_id="manager", role="manager", scopes=("customer:any:read",)),
    ]
    for auth in identities:
        with pytest.raises(PermissionError, match="administrador"):
            test_harness.handle_message(
                ChatRequest(session_id=f"denied-{auth.role}", customer_id="123", message="Desbloqueie meu cartão"),
                auth=auth,
            )


def test_card_unlock_is_idempotent() -> None:
    mock_bank_service.reset()

    first = mock_bank_service.unlock_card("123")
    second = mock_bank_service.unlock_card("123")

    assert first == {"customer_id": "123", "card_status": "ACTIVE", "changed": False}
    assert second == first
    history = mock_bank_service.get_service_history("123")
    assert history[-1] == {"action": "CARD_UNLOCK", "changed": False}


def test_low_value_pix_executes_without_confirmation() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-5",
            "customer_id": "123",
            "message": "Quero fazer um pix de 100 para chave pix maria@example.com",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "transaction"
    assert body["requires_confirmation"] is False
    assert body["balance"] == 24900.0
    assert body["pix_details"]["destination_key"] == "maria@example.com"


def test_pix_collects_missing_destination_before_execution() -> None:
    first_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-pix-collect-destination",
            "customer_id": "123",
            "message": "Quero fazer um pix de 250",
        },
    )

    assert first_response.status_code == 200
    first_body = first_response.json()
    assert first_body["route"] == "transaction"
    assert first_body["requires_confirmation"] is False
    assert first_body["pending_operation"] == "collect_pix_details"
    assert "chave pix" in first_body["message"].lower()
    assert first_body["pix_details"]["amount"] == 250.0

    second_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-pix-collect-destination",
            "customer_id": "123",
            "message": "A chave pix e maria@example.com",
        },
    )

    assert second_response.status_code == 200
    second_body = second_response.json()
    assert second_body["route"] == "transaction"
    assert second_body["requires_confirmation"] is False
    assert second_body["balance"] == 24750.0
    assert second_body["pix_details"]["destination_key"] == "maria@example.com"


def test_pix_draft_accepts_bare_email_as_destination_followup() -> None:
    first_response = client.post(
        "/v1/channels/app/chat",
        headers=_demo_auth_headers(settings.demo_customer_token),
        json={
            "session_id": "sess-pix-bare-email-followup",
            "customer_id": "123",
            "message": "Quero fazer um PIX de 7000 para chave pix",
        },
    )
    assert first_response.status_code == 200
    assert first_response.json()["pending_operation"] == "collect_pix_details"

    second_response = client.post(
        "/v1/channels/app/chat",
        headers=_demo_auth_headers(settings.demo_customer_token),
        json={
            "session_id": "sess-pix-bare-email-followup",
            "customer_id": "123",
            "message": "maria@example.com",
        },
    )

    assert second_response.status_code == 200
    body = second_response.json()
    assert body["route"] == "transaction"
    assert body["pending_operation"] == "create_pix"
    assert body["requires_confirmation"] is True
    assert body["pix_details"]["amount"] == 7000.0
    assert body["pix_details"]["destination_key"] == "maria@example.com"
    assert body["observability"]["planner"]["provider"] == "not_called"


def test_high_value_pix_collects_data_before_hitl_checkpoint() -> None:
    first_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-pix-collect-high-value",
            "customer_id": "123",
            "message": "Quero fazer um pix de 7000",
        },
    )

    assert first_response.status_code == 200
    first_body = first_response.json()
    assert first_body["pending_operation"] == "collect_pix_details"
    assert first_body["requires_confirmation"] is False

    second_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-pix-collect-high-value",
            "customer_id": "123",
            "message": "Chave pix maria@example.com",
        },
    )

    assert second_response.status_code == 200
    second_body = second_response.json()
    assert second_body["pending_operation"] == "create_pix"
    assert second_body["requires_confirmation"] is True
    assert second_body["pix_details"]["amount"] == 7000.0
    assert second_body["pix_details"]["destination_key"] == "maria@example.com"


def test_pix_above_daily_limit_is_blocked_before_hitl() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-pix-daily-limit",
            "customer_id": "123",
            "message": "Faca um PIX de 50001 para chave pix maria@example.com",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "transaction"
    assert body["requires_confirmation"] is False
    assert body["pending_operation"] == "pix_policy_review"
    assert "limite diario" in body["message"].lower()
    assert body["pix_details"]["amount"] == 50001.0


def test_pix_suspicious_key_is_blocked_with_alert() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-pix-suspicious-key",
            "customer_id": "123",
            "message": "Quero fazer um pix de 100 para chave pix golpe@example.com",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "transaction"
    assert body["requires_confirmation"] is False
    assert body["pending_operation"] == "pix_policy_review"
    assert "pix suspeito" in body["message"].lower()
    assert body["balance"] is None


def test_pix_with_sensitive_credentials_is_blocked() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-pix-sensitive-credential",
            "customer_id": "123",
            "message": "Quero fazer um pix de 100 para chave pix maria@example.com minha senha e 123456",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "transaction"
    assert body["requires_confirmation"] is False
    assert body["pending_operation"] == "pix_policy_review"
    assert "nao envie senha" in body["message"].lower()
    assert body["balance"] is None


def test_documental_tariff_question_returns_grounded_source() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-rag-1",
            "customer_id": "123",
            "message": "Onde consulto tarifas e pacotes de servicos?",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "faq_fast_path"
    assert ".docs/tabela_geral_de_tarifas_pf_pdf.pdf" in body["grounding_sources"]
    assert "tarifas e pacotes" in body["message"].lower()
    assert "tambem posso te ajudar por aqui" in body["message"].lower()
    assert "painel tecnico" not in body["message"].lower()
    assert "tabela geral de tarifas" not in body["message"].lower()
    assert "pagina" not in body["message"].lower()
    assert "referencia" not in body["message"].lower()


def test_documental_tariff_answer_avoids_raw_pdf_table_dump() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-rag-saque",
            "customer_id": "123",
            "message": "Tem tarifa para saque?",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "faq_fast_path"
    assert ".docs/tabela_geral_de_tarifas_pf_pdf.pdf" in body["grounding_sources"]
    assert "saques" in body["message"].lower()
    assert "a tarifa pode variar" in body["message"].lower()
    assert "fonte recuperada" not in body["message"].lower()
    assert "trecho usado" not in body["message"].lower()
    assert "tabela geral de tarifas" not in body["message"].lower()
    assert "pagina" not in body["message"].lower()
    assert "referencia" not in body["message"].lower()


def test_documental_tariff_followup_keeps_controlled_customer_answer() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-rag-saque-followup",
            "customer_id": "123",
            "message": "Saque!",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "faq_fast_path"
    assert ".docs/tabela_geral_de_tarifas_pf_pdf.pdf" in body["grounding_sources"]
    assert "saques" in body["message"].lower()
    assert "banco24horas" in body["message"].lower()
    assert "trecho usado" not in body["message"].lower()
    assert "correntistas tem direito" not in body["message"].lower()
    assert "tabela geral de tarifas" not in body["message"].lower()
    assert "pagina" not in body["message"].lower()
    assert "referencia" not in body["message"].lower()


def test_documental_tariff_followup_with_context_does_not_loop() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-rag-saque-conta-corrente",
            "customer_id": "123",
            "message": "Saque conta corrente.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "faq_fast_path"
    assert ".docs/tabela_geral_de_tarifas_pf_pdf.pdf" in body["grounding_sources"]
    assert "saques em conta corrente" in body["message"].lower() or "saque em conta corrente" in body["message"].lower()
    assert "tarifas e pacotes" in body["message"].lower()
    assert "me diga o contexto" not in body["message"].lower()
    assert "trecho usado" not in body["message"].lower()
    assert "tabela geral de tarifas" not in body["message"].lower()
    assert "pagina" not in body["message"].lower()
    assert "referencia" not in body["message"].lower()


def test_documental_tariff_context_followup_reuses_previous_question() -> None:
    session_id = "sess-rag-context-memory"
    first_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": session_id,
            "customer_id": "123",
            "message": "Tem tarifa para saque?",
        },
    )
    assert first_response.status_code == 200

    followup_response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": session_id,
            "customer_id": "123",
            "message": "Conta corrente",
        },
    )

    assert followup_response.status_code == 200
    body = followup_response.json()
    assert body["route"] == "faq_fast_path"
    assert ".docs/tabela_geral_de_tarifas_pf_pdf.pdf" in body["grounding_sources"]
    assert "saque" in body["message"].lower()
    assert "conta corrente" in body["message"].lower()
    assert "trecho usado" not in body["message"].lower()
    assert "produtos/servicos incluidos" not in body["message"].lower()
    assert "tabela geral de tarifas" not in body["message"].lower()
    assert "pagina" not in body["message"].lower()


def test_essential_package_multiturn_does_not_repeat_generic_tariff_prompt() -> None:
    session_id = "sess-essential-package-memory"
    messages = [
        "Me fala sobre tarifas da conta corrente, por favor.",
        "Pacote essencial.",
        "Me fala sobre o pacote essencial para conta corrente.",
    ]

    responses = [
        client.post(
            "/v1/channels/app/chat",
            json={"session_id": session_id, "customer_id": "123", "message": message},
        )
        for message in messages
    ]

    assert all(response.status_code == 200 for response in responses)
    for response in responses[1:]:
        message = response.json()["message"]
        assert "não tem mensalidade" in message
        assert "4 saques" in message
        assert "diga o servico e o canal" not in message.lower()
        assert response.json()["observability"]["llm"]["provider"] == "disabled"
        timings = response.json()["observability"]["timings"]
        assert timings["retrieval_ms"] >= 0
        assert timings["provider_ms"] == 0
        assert timings["composition_ms"] >= 0
        assert timings["knowledge_total_ms"] >= timings["retrieval_ms"]


def test_documental_memory_does_not_overwrite_pending_pix_checkpoint(tmp_path) -> None:  # noqa: ANN001
    store = CheckpointStore(tmp_path / "checkpoints.json")
    store.save_pending_pix(
        "shared-session",
        PendingPixOperation(customer_id="123", amount=7000.0, destination_key="maria@example.com"),
    )

    store.save_documental_draft("shared-session", {"last_query": "Tem tarifa para saque?"})

    pending = store.get_pending_pix("shared-session")
    assert pending is not None
    assert pending.amount == 7000.0
    assert store.get_documental_draft("shared-session") is None


def test_knowledge_status_reports_ingested_tariff_pdf() -> None:
    response = client.get("/v1/mcp/knowledge/status", headers=INTERNAL_TOOL_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["pdf_ingested"] is True
    assert body["web_sources_loaded"] is True
    assert body["reranker"] == "local-intent-reranker"
    assert body["document_count"] > 3
    assert ".docs/tabela_geral_de_tarifas_pf_pdf.pdf" in body["sources"]


def test_documental_help_center_question_returns_official_source() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-rag-help-center",
            "customer_id": "123",
            "message": "Como falo com o Itau pelo WhatsApp?",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "faq_fast_path"
    assert "https://www.itau.com.br/atendimento-itau/para-voce" in body["grounding_sources"]
    assert body["grounding_sources"] == ["https://www.itau.com.br/atendimento-itau/para-voce"]
    assert "nao encontrei contexto oficial suficiente" not in body["message"].lower()
    assert "pergunta do cliente" not in body["message"].lower()
    assert "contexto oficial aprovado" not in body["message"].lower()
    assert "hybrid_retrieve" in body["observability"]["tools_called"]
    assert body["observability"]["llm"]["provider"]
    assert body["observability"]["retrieval"]["approved_context"]


def test_grounded_faq_synthesizer_receives_only_retrieved_official_context() -> None:
    synthesizer = RecordingSynthesizer()
    service = GroundedKnowledgeService(synthesizer=synthesizer)

    message, sources = service.answer("Como falo com o Itau pelo WhatsApp?")

    assert message.startswith("Resposta sintetizada somente com contexto oficial recuperado.")
    assert message.endswith("Posso ajudar com mais alguma dúvida?")
    assert sources == ["https://www.itau.com.br/atendimento-itau/para-voce"]
    assert synthesizer.calls == [
        ("Como falo com o Itau pelo WhatsApp?", ["https://www.itau.com.br/atendimento-itau/para-voce"])
    ]


def test_grounded_faq_synthesizer_is_not_called_without_official_context() -> None:
    synthesizer = RecordingSynthesizer()
    service = GroundedKnowledgeService(synthesizer=synthesizer)

    message, sources = service.answer("Qual e a cotacao do dolar comercial agora?")

    assert sources == []
    assert "nao encontrei contexto oficial suficiente" in message.lower()
    assert synthesizer.calls == []


def test_local_fallback_uses_customer_service_voice_for_policy_question() -> None:
    from app.services.knowledge.llm import LocalGroundedFaqSynthesizer
    from app.services.knowledge.schemas import RetrievedKnowledge

    synthesizer = LocalGroundedFaqSynthesizer("provider-fallback-local")
    response = synthesizer.synthesize(
        "Quais sao as politicas do Itau?",
        [
            RetrievedKnowledge(
                title="Politicas institucionais",
                source="https://www.itau.com.br/relacoes-com-investidores/politicas/",
                text="Politicas de governanca, integridade, etica e ESG.",
                score=1.0,
            )
        ],
    )

    assert response.startswith("Claro!")
    assert "politicas institucionais do Itau" in response
    assert "Posso te orientar assim" not in response


def test_tariff_answer_uses_controlled_fast_path_when_synthesizer_is_available() -> None:
    synthesizer = RecordingSynthesizer()
    service = GroundedKnowledgeService(synthesizer=synthesizer)

    message, sources = service.answer("Tem tarifa para saque?")

    assert ".docs/tabela_geral_de_tarifas_pf_pdf.pdf" in sources
    assert "saques" in message.lower()
    assert "a tarifa pode variar" in message.lower()
    assert synthesizer.calls == []


def test_tariff_answer_does_not_wait_for_provider_fallback() -> None:
    synthesizer = FallbackRecordingSynthesizer()
    service = GroundedKnowledgeService(synthesizer=synthesizer)

    result = service.answer_with_trace("Tem tarifa para saque?")

    assert ".docs/tabela_geral_de_tarifas_pf_pdf.pdf" in result["sources"]
    assert "saques" in result["message"].lower()
    assert "a tarifa pode variar" in result["message"].lower()
    assert "trecho bruto" not in result["message"].lower()
    assert "tabela geral de tarifas" not in result["message"].lower()
    assert "pagina" not in result["message"].lower()
    assert "referencia" not in result["message"].lower()
    assert "controlled_tariff_answer_builder" in result["observability"]["tools_called"]
    assert synthesizer.calls == []


def test_openai_grounded_synthesizer_falls_back_without_api_key(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "openai_api_key", None)
    synthesizer = OpenAIGroundedFaqSynthesizer()
    service = GroundedKnowledgeService(synthesizer=synthesizer)

    message, sources = service.answer("Como falo com o Itau pelo WhatsApp?")

    assert sources == ["https://www.itau.com.br/atendimento-itau/para-voce"]
    assert message.startswith("Claro!")
    assert "canal oficial de atendimento do Itau" in message
    assert "fontes oficiais recuperadas" not in message.lower()
    assert "fonte" not in message.lower()
    assert synthesizer.last_trace["provider"] == "openai-responses"
    assert synthesizer.last_trace["fallback_used"] is True
    assert synthesizer.last_trace["fallback_reason"] == "missing_api_key"
    assert synthesizer.last_trace["prompt"]
    assert synthesizer.last_trace["approved_context"]


def test_openai_grounded_prompt_contains_only_question_and_official_context() -> None:
    synthesizer = OpenAIGroundedFaqSynthesizer()
    service = GroundedKnowledgeService(synthesizer=RecordingSynthesizer())
    _, sources = service.answer("Como falo com o Itau pelo WhatsApp?")
    assert sources == ["https://www.itau.com.br/atendimento-itau/para-voce"]

    retrieved = service._reranker.rerank(  # noqa: SLF001
        "Como falo com o Itau pelo WhatsApp?",
        service._retriever.retrieve("Como falo com o Itau pelo WhatsApp?", top_k=6),  # noqa: SLF001
    )[:2]
    prompt = synthesizer._build_user_prompt("Como falo com o Itau pelo WhatsApp?", retrieved)  # noqa: SLF001

    assert "Customer question: Como falo com o Itau pelo WhatsApp?" in prompt
    assert "https://www.itau.com.br/atendimento-itau/para-voce" in prompt
    assert "Do not cite sources" in prompt
    assert "checkpoint" not in prompt.lower()
    assert "customer_id" not in prompt.lower()


def test_grounded_synthesizer_rejects_prompt_echo_as_customer_answer() -> None:
    synthesizer = OpenAIGroundedFaqSynthesizer()

    assert synthesizer._looks_like_prompt_echo(  # noqa: SLF001
        "Pergunta do cliente: Tem tarifa para saque? Contexto oficial aprovado pelo Harness..."
    )


def test_docker_model_runner_provider_is_selectable(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "llm_grounded_faq_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "docker_model_runner")
    monkeypatch.setattr(settings, "docker_model_runner_model", "ai/smollm2")

    synthesizer = build_grounded_faq_synthesizer()

    assert isinstance(synthesizer, DockerModelRunnerGroundedFaqSynthesizer)
    assert synthesizer.provider_name == "docker-model-runner"


def test_mcp_server_module_exposes_safe_agent_tools() -> None:
    from app.mcp import server as mcp_server

    assert mcp_server.mcp is not None
    status = mcp_server.get_demo_status()
    assert status["knowledge"]["pdf_ingested"] is True
    assert any(tool["name"] == "create_pix" and tool["requires_hitl"] for tool in status["tools"])
    assert any(resource["uri"] == "itau://knowledge/tariff-pdf" for resource in status["resources"])


def test_mcp_streamable_http_client_smoke() -> None:
    port = _find_free_port()
    env = os.environ.copy()
    env["MCP_SERVER_HOST"] = "127.0.0.1"
    env["MCP_SERVER_PORT"] = str(port)
    process = subprocess.Popen(
        [sys.executable, "-m", "app.mcp.server"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_tcp("127.0.0.1", port)
        result = asyncio.run(run_smoke(f"http://127.0.0.1:{port}/mcp"))
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    assert "send_agent_message" in result["tools"]
    assert "itau://knowledge/resources" in result["resources"]
    assert result["pdf_ingested"] is True


def test_documental_policy_question_returns_official_source() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-rag-policy",
            "customer_id": "123",
            "message": "Onde encontro politicas de governanca e integridade do Itau?",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "faq_fast_path"
    assert "https://www.itau.com.br/relacoes-com-investidores/politicas/" in body["grounding_sources"]
    assert "politicas" in body["message"].lower()
    assert "nao encontrei contexto oficial suficiente" not in body["message"].lower()
    assert "pergunta do cliente" not in body["message"].lower()
    assert "contexto oficial aprovado" not in body["message"].lower()


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_tcp(host: str, port: int, timeout_seconds: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            if sock.connect_ex((host, port)) == 0:
                return
        time.sleep(0.25)
    raise TimeoutError(f"MCP server did not accept TCP connections on {host}:{port}.")


def test_documental_question_without_context_fails_safely() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-rag-2",
            "customer_id": "123",
            "message": "Qual e a cotacao do dolar comercial agora?",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "faq_fast_path"
    assert body["grounding_sources"] == []
    assert "nao encontrei contexto oficial suficiente" in body["message"].lower()


def test_confirmation_cannot_be_reused_after_pending_operation_is_consumed() -> None:
    client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-6",
            "customer_id": "123",
            "message": "Quero fazer um pix de 7000 para chave pix maria@example.com",
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
            message="Quero fazer um pix de 7000 para chave pix maria@example.com",
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


def test_observability_status_reports_langsmith_configuration() -> None:
    response = client.get("/v1/mcp/observability/status", headers=INTERNAL_TOOL_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert "langsmith" in body
    assert "available" in body["langsmith"]
    assert "enabled" in body["langsmith"]


def test_pix_emits_append_only_audit_event() -> None:
    response = client.post(
        "/v1/channels/app/chat",
        json={
            "session_id": "sess-7",
            "customer_id": "123",
            "message": "Quero fazer um pix de 100 para chave pix maria@example.com",
        },
    )
    assert response.status_code == 200

    audit_response = client.get("/v1/mcp/audit/123", headers=INTERNAL_TOOL_HEADERS)
    assert audit_response.status_code == 200
    audit_body = audit_response.json()
    assert audit_body[-1]["event_type"] == "PIX"
    assert audit_body[-1]["payload"]["amount"] == 100.0
    assert audit_body[-1]["payload"]["destination_key"] == "maria@example.com"
    assert audit_body[-1]["user"] == "local-demo-customer-123"
    assert audit_body[-1]["customer_id"] == "123"
    assert audit_body[-1]["actor_role"] == "customer"
    assert audit_body[-1]["session_id"] == "sess-7"
    assert audit_body[-1]["action"] == "PIX"
    assert audit_body[-1]["amount"] == 100.0
    assert audit_body[-1]["timestamp"]
    assert len(audit_body[-1]["event_hash"]) == 64


def test_audit_context_idempotency_and_integrity() -> None:
    context = AuditExecutionContext(
        actor_id="manager-demo",
        actor_role="manager",
        customer_id="456",
        session_id="audit-session",
        trace_id="audit-trace",
    )
    with audit_execution_scope(context):
        first = audit_log_service.append(
            "456",
            "BALANCE_ACCESS",
            {"result": "allowed"},
            status="executed",
            idempotency_key="audit-idempotent-1",
        )
        duplicate = audit_log_service.append(
            "456",
            "BALANCE_ACCESS",
            {"result": "allowed"},
            status="executed",
            idempotency_key="audit-idempotent-1",
        )

    assert first["event_id"] == duplicate["event_id"]
    assert first["actor_id"] == "manager-demo"
    assert first["actor_role"] == "manager"
    assert first["session_id"] == "audit-session"
    assert first["trace_id"] == "audit-trace"
    assert audit_log_service.verify_integrity() == {
        "valid": True,
        "event_count": 1,
        "failed_event_id": None,
    }
    audit_log_service._events[0]["payload"]["result"] = "tampered"  # noqa: SLF001
    tampered = audit_log_service.verify_integrity()
    assert tampered["valid"] is False
    assert tampered["failed_event_id"] == first["event_id"]
