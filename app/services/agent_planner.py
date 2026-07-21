from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Protocol

from app.config import settings
from app.graph.state import WorkflowRoute
from app.services.intent_router import IntentRouter
from app.services.prompt_registry import PromptRegistry, prompt_registry


TOOL_TO_ROUTE: dict[str, WorkflowRoute] = {
    "search_official_knowledge": "faq_fast_path",
    "get_customer_balance": "core_banking_balance",
    "manage_card_limit": "core_banking_limit",
    "prepare_pix_transfer": "transaction",
    "protect_customer_account": "emergency",
}

PLANNER_TOOLS = [
    {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Motivo curto, sem dados sensiveis, para selecionar esta capability.",
                }
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
        "strict": True,
    }
    for name, description in {
        "search_official_knowledge": "Responder duvidas usando apenas a base oficial aprovada.",
        "get_customer_balance": "Consultar o saldo da conta solicitada pelo cliente.",
        "manage_card_limit": "Consultar limite ou iniciar uma solicitacao de aumento de limite.",
        "prepare_pix_transfer": "Coletar dados e preparar uma transferencia Pix sujeita a politicas e HITL.",
        "protect_customer_account": "Priorizar fraude, roubo, perda ou bloqueio preventivo do cartao.",
    }.items()
]


class Planner(Protocol):
    last_trace: dict

    def classify(self, message: str) -> WorkflowRoute: ...


@dataclass
class DeterministicPlanner:
    router: IntentRouter = field(default_factory=IntentRouter)
    last_trace: dict = field(default_factory=dict)

    def classify(self, message: str) -> WorkflowRoute:
        route = self.router.classify(message)
        self.last_trace = {
            "provider": "deterministic-router",
            "model": None,
            "selected_tool": self._tool_for_route(route),
            "route": route,
            "fallback_used": False,
            "fallback_reason": None,
            "prompt_profile": None,
            "prompt_version": None,
            "token_usage": None,
            "duration_ms": 0,
        }
        return route

    def _tool_for_route(self, route: WorkflowRoute) -> str:
        return next(name for name, mapped_route in TOOL_TO_ROUTE.items() if mapped_route == route)


class OpenAIResponsesPlanner:
    def __init__(
        self,
        fallback: Planner | None = None,
        prompts: PromptRegistry | None = None,
    ) -> None:
        self._fallback = fallback or DeterministicPlanner()
        self._prompts = prompts or prompt_registry
        self.last_trace: dict = {}

    def classify(self, message: str) -> WorkflowRoute:
        start = time.perf_counter()
        prompt = self._prompts.load("planner", "system")
        if not settings.openai_api_key:
            return self._fallback_route(message, prompt, start, "missing_api_key")

        try:
            from openai import OpenAI

            response = OpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.llm_timeout_seconds,
                max_retries=0,
            ).responses.create(
                model=settings.llm_model,
                reasoning={"effort": settings.llm_reasoning_effort},
                input=[
                    {"role": "developer", "content": prompt},
                    {"role": "user", "content": message},
                ],
                tools=PLANNER_TOOLS,
                tool_choice="required",
            )
            selected = self._extract_tool_call(response)
            route = TOOL_TO_ROUTE.get(selected["name"])
            if route is None:
                return self._fallback_route(message, prompt, start, "unknown_tool")
            self.last_trace = {
                "provider": "openai-responses",
                "model": settings.llm_model,
                "selected_tool": selected["name"],
                "tool_arguments": selected["arguments"],
                "route": route,
                "fallback_used": False,
                "fallback_reason": None,
                "prompt": prompt,
                "prompt_profile": self._prompts.profile,
                "prompt_version": self._prompts.version,
                "prompt_hash": self._prompts.digest("planner", "system"),
                "token_usage": self._extract_usage(response),
                "duration_ms": round((time.perf_counter() - start) * 1000),
            }
            return route
        except Exception as exc:  # noqa: BLE001
            return self._fallback_route(message, prompt, start, f"provider_error:{type(exc).__name__}")

    def _extract_tool_call(self, response: object) -> dict:
        for item in getattr(response, "output", []):
            if getattr(item, "type", None) != "function_call":
                continue
            arguments = getattr(item, "arguments", "{}") or "{}"
            parsed = json.loads(arguments)
            if not isinstance(parsed, dict):
                raise ValueError("Planner tool arguments must be an object.")
            return {"name": str(getattr(item, "name", "")), "arguments": parsed}
        raise ValueError("Planner response did not contain a function call.")

    def _fallback_route(self, message: str, prompt: str, start: float, reason: str) -> WorkflowRoute:
        route = self._fallback.classify(message)
        fallback_trace = getattr(self._fallback, "last_trace", {}) or {}
        self.last_trace = {
            "provider": "openai-responses",
            "model": settings.llm_model,
            "selected_tool": None,
            "fallback_selected_tool": fallback_trace.get("selected_tool"),
            "route": route,
            "fallback_used": True,
            "fallback_reason": reason,
            "fallback_provider": fallback_trace.get("provider", "deterministic-router"),
            "prompt": prompt,
            "prompt_profile": self._prompts.profile,
            "prompt_version": self._prompts.version,
            "prompt_hash": self._prompts.digest("planner", "system"),
            "token_usage": None,
            "duration_ms": round((time.perf_counter() - start) * 1000),
        }
        return route

    def _extract_usage(self, response: object) -> dict | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        return usage if isinstance(usage, dict) else None


def build_agent_planner() -> Planner:
    if settings.agentic_planner_enabled and settings.llm_provider == "openai":
        return OpenAIResponsesPlanner()
    return DeterministicPlanner()
