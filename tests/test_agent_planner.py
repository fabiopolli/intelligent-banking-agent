from __future__ import annotations

import sys
from types import SimpleNamespace

from app.config import settings
from app.services.agent_planner import (
    DeterministicPlanner,
    DockerModelRunnerPlanner,
    OpenAIResponsesPlanner,
)
from app.schemas.messages import ChatRequest
from app.services.harness import DemoHarness
from app.services.internal_systems import LocalInternalSystemsGateway


def _fake_response(tool_name: str):
    return SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name=tool_name,
                arguments='{"reason":"capability adequada"}',
            )
        ],
        usage=SimpleNamespace(model_dump=lambda: {"input_tokens": 20, "output_tokens": 5}),
    )


def _fake_chat_response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(model_dump=lambda: {"prompt_tokens": 12, "completion_tokens": 3}),
    )


def test_docker_model_runner_planner_selects_registered_capability(monkeypatch) -> None:  # noqa: ANN001
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):  # noqa: ANN003, ANN201
            captured.update(kwargs)
            return _fake_chat_response("prepare_pix_transfer")

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    planner = DockerModelRunnerPlanner()

    route = planner.classify("Quero fazer um Pix")

    assert route == "transaction"
    assert captured["model"] == settings.docker_model_runner_model
    assert captured["client"]["timeout"] == settings.docker_model_runner_timeout_seconds
    assert planner.last_trace["provider"] == "docker-model-runner"
    assert planner.last_trace["fallback_used"] is False


def test_openai_planner_falls_back_through_gemma_before_deterministic(monkeypatch) -> None:  # noqa: ANN001
    class FailingResponses:
        @staticmethod
        def create(**kwargs):  # noqa: ANN003, ANN205
            raise TimeoutError("openai unavailable")

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):  # noqa: ANN003, ANN205
            return _fake_chat_response("get_customer_balance")

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.responses = FailingResponses()
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-real")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    planner = OpenAIResponsesPlanner()

    route = planner.classify("Qual e o meu saldo?")

    assert route == "core_banking_balance"
    assert planner.last_trace["fallback_provider"] == "docker-model-runner"


def test_request_override_forces_docker_model_runner_planner() -> None:
    class RecordingPlanner:
        def __init__(self, provider: str, route: str) -> None:
            self.calls = []
            self.route = route
            self.last_trace = {"provider": provider}

        def classify(self, message):  # noqa: ANN001, ANN201
            self.calls.append(message)
            return self.route

    configured = RecordingPlanner("configured-test", "faq_fast_path")
    docker = RecordingPlanner("docker-model-runner", "core_banking_balance")
    result = DemoHarness(
        router=configured,
        docker_router=docker,
        internal_systems=LocalInternalSystemsGateway(),
    ).handle_message(
        ChatRequest(
            session_id="forced-docker-planner",
            customer_id="123",
            message="Quanto dinheiro tenho disponível?",
            llm_provider="docker_model_runner",
        )
    )

    assert result["route"] == "core_banking"
    assert configured.calls == []
    assert docker.calls == ["Quanto dinheiro tenho disponível?"]
    assert result["observability"]["planner"]["provider"] == "docker-model-runner"


def test_explicit_pix_uses_native_router_without_any_llm() -> None:
    class MustNotRunPlanner:
        last_trace = {}

        def classify(self, message):  # noqa: ANN001, ANN201
            raise AssertionError("Explicit Pix must not call an LLM planner.")

    result = DemoHarness(
        router=MustNotRunPlanner(),
        docker_router=MustNotRunPlanner(),
        internal_systems=LocalInternalSystemsGateway(),
    ).handle_message(
        ChatRequest(
            session_id="native-pix-router",
            customer_id="123",
            message="Quero fazer um PIX de 7000 para chave pix maria@example.com",
            llm_provider="docker_model_runner",
        )
    )

    assert result["route"] == "transaction"
    assert result["requires_confirmation"] is True
    assert result["observability"]["planner"]["provider"] == "deterministic-native-router"


def test_openai_planner_selects_registered_balance_tool(monkeypatch) -> None:  # noqa: ANN001
    captured = {}

    class FakeResponses:
        def create(self, **kwargs):  # noqa: ANN003, ANN201
            captured.update(kwargs)
            return _fake_response("get_customer_balance")

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            captured["client"] = kwargs
            self.responses = FakeResponses()

    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-real")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    planner = OpenAIResponsesPlanner()

    route = planner.classify("Qual e o meu saldo?")

    assert route == "core_banking_balance"
    assert captured["model"] == settings.llm_model
    assert captured["tool_choice"] == "required"
    assert captured["reasoning"] == {"effort": settings.llm_reasoning_effort}
    assert planner.last_trace["selected_tool"] == "get_customer_balance"
    assert planner.last_trace["fallback_used"] is False
    assert planner.last_trace["token_usage"]["input_tokens"] == 20


def test_openai_planner_falls_back_on_unknown_tool(monkeypatch) -> None:  # noqa: ANN001
    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.responses = SimpleNamespace(create=lambda **call: _fake_response("delete_account"))

    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-real")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    planner = OpenAIResponsesPlanner(fallback=DeterministicPlanner())

    route = planner.classify("Quero fazer um pix de 100 reais")

    assert route == "transaction"
    assert planner.last_trace["fallback_used"] is True
    assert planner.last_trace["fallback_reason"] == "unknown_tool"
    assert planner.last_trace["fallback_provider"] == "deterministic-router"


def test_openai_planner_falls_back_when_provider_fails(monkeypatch) -> None:  # noqa: ANN001
    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.responses = SimpleNamespace(create=self._fail)

        @staticmethod
        def _fail(**kwargs):  # noqa: ANN003, ANN205
            raise TimeoutError("provider unavailable")

    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-real")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    planner = OpenAIResponsesPlanner()

    route = planner.classify("Fui roubado")

    assert route == "emergency"
    assert planner.last_trace["fallback_used"] is True
    assert planner.last_trace["fallback_reason"] == "provider_error:TimeoutError"


def test_prompt_registry_metadata_is_traced(monkeypatch) -> None:  # noqa: ANN001
    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            self.responses = SimpleNamespace(
                create=lambda **call: _fake_response("search_official_knowledge")
            )

    monkeypatch.setattr(settings, "openai_api_key", "test-key-not-real")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    planner = OpenAIResponsesPlanner()

    planner.classify("Qual a taxa do consignado?")

    assert planner.last_trace["prompt_profile"] == "banking-v1"
    assert planner.last_trace["prompt_version"] == "1.1.0"
    assert len(planner.last_trace["prompt_hash"]) == 12


def test_sensitive_credentials_are_blocked_before_planner() -> None:
    class MustNotRunPlanner:
        last_trace = {}

        def classify(self, message):  # noqa: ANN001, ANN201
            raise AssertionError("Planner must not receive sensitive credentials.")

    result = DemoHarness(router=MustNotRunPlanner()).handle_message(
        ChatRequest(
            session_id="sensitive-pre-llm",
            customer_id="123",
            message="Meu iToken e 123456 e quero fazer um Pix",
        )
    )

    assert result["pending_operation"] == "pix_policy_review"
    assert result["observability"]["guardrails"]["stage"] == "pre_llm_ingress"
    assert result["observability"]["planner"]["provider"] == "not_called"


def test_greeting_and_introduction_use_social_fast_path_without_planner() -> None:
    class MustNotRunPlanner:
        last_trace = {}

        def classify(self, message):  # noqa: ANN001, ANN201
            raise AssertionError("Planner must not run for a social message.")

    result = DemoHarness(router=MustNotRunPlanner()).handle_message(
        ChatRequest(
            session_id="social-greeting",
            customer_id="123",
            message="Olá, meu nome é Fabio",
        )
    )

    assert result["route"] == "social_fast_path"
    assert result["message"].startswith("Olá, Fabio!")
    assert "saldo" in result["message"].lower()
    assert result["grounding_sources"] == []
    assert result["observability"]["planner"]["provider"] == "not_called"
    assert result["observability"]["llm"]["provider"] == "not_called"
    assert result["observability"]["retrieval"]["candidate_count"] == 0


def test_greeting_with_banking_intent_does_not_hide_requested_operation() -> None:
    result = DemoHarness(router=DeterministicPlanner()).handle_message(
        ChatRequest(
            session_id="social-with-balance",
            customer_id="123",
            message="Olá, qual é o meu saldo?",
        )
    )

    assert result["route"] == "core_banking"
    assert "saldo" in result["message"].lower()
