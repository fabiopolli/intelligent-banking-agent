from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Protocol

from app.config import settings
from app.services.knowledge.schemas import RetrievedKnowledge
from app.services.prompt_registry import PromptRegistry, prompt_registry

logger = logging.getLogger(__name__)


class GroundedFaqSynthesizer(Protocol):
    provider_name: str
    last_trace: dict

    def synthesize(self, query: str, contexts: list[RetrievedKnowledge]) -> str:
        """Return a customer-facing answer using only approved retrieved contexts."""


@dataclass
class LocalGroundedFaqSynthesizer:
    provider_name: str = "local-deterministic"
    last_trace: dict = field(default_factory=dict)

    def synthesize(self, query: str, contexts: list[RetrievedKnowledge]) -> str:
        start = time.perf_counter()
        primary = contexts[0]
        message = self._customer_service_fallback(query, primary)
        self.last_trace = {
            "provider": self.provider_name,
            "model": "local-deterministic",
            "fallback_used": self.provider_name != "local-deterministic",
            "prompt": self._build_local_prompt(query),
            "approved_context": self._context_trace(contexts),
            "token_usage": None,
            "duration_ms": round((time.perf_counter() - start) * 1000),
        }
        return message

    def _customer_service_fallback(self, query: str, primary: RetrievedKnowledge) -> str:
        normalized_query = query.lower()
        if "politica" in normalized_query or "governanca" in normalized_query:
            return (
                "Claro! As politicas institucionais do Itau reunem diretrizes sobre governanca "
                "corporativa, integridade, etica, ESG e temas regulatorios. Se voce me disser qual "
                "desses assuntos quer consultar, eu direciono a informacao com mais precisao."
            )
        if "whatsapp" in normalized_query or "atendimento" in normalized_query:
            return (
                "Claro! Posso te ajudar a encontrar o canal oficial de atendimento do Itau mais "
                "adequado. Me diga se voce precisa falar sobre conta, cartao, Pix ou outro produto."
            )
        return (
            "Claro! Encontrei uma orientacao oficial do Itau relacionada ao que voce perguntou: "
            f"{self._compact(primary.text)} Se quiser, posso te ajudar a detalhar esse assunto."
        )

    def _compact(self, text: str, limit: int = 260) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit].rstrip()}..."

    def _build_local_prompt(self, query: str) -> str:
        return f"Local deterministic grounded synthesis for query: {query}"

    def _context_trace(self, contexts: list[RetrievedKnowledge]) -> list[dict]:
        return [
            {
                "title": item.title,
                "source": item.source,
                "score": item.score,
                "excerpt": self._compact(item.text, limit=360),
            }
            for item in contexts
        ]


class OpenAIGroundedFaqSynthesizer:
    provider_name = "openai-responses"

    def __init__(
        self,
        fallback: GroundedFaqSynthesizer | None = None,
        prompts: PromptRegistry | None = None,
    ) -> None:
        self._fallback = fallback or LocalGroundedFaqSynthesizer("openai-fallback-local")
        self._prompts = prompts or prompt_registry
        self.last_trace: dict = {}

    def synthesize(self, query: str, contexts: list[RetrievedKnowledge]) -> str:
        start = time.perf_counter()
        prompt = self._build_user_prompt(query, contexts)
        if not settings.openai_api_key:
            message = self._fallback.synthesize(query, contexts)
            self.last_trace = self._fallback_trace(prompt, contexts, start, "missing_api_key")
            return message

        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("OpenAI SDK is not installed; using local grounded FAQ fallback.")
            message = self._fallback.synthesize(query, contexts)
            self.last_trace = self._fallback_trace(prompt, contexts, start, "missing_sdk")
            return message

        try:
            client = OpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.llm_timeout_seconds,
                max_retries=0,
            )
            response = client.responses.create(
                model=settings.llm_model,
                input=[
                    {
                        "role": "developer",
                        "content": self._prompts.load("knowledge", "system"),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI grounded FAQ synthesis failed; using local fallback: %s", exc)
            message = self._fallback.synthesize(query, contexts)
            self.last_trace = self._fallback_trace(prompt, contexts, start, "provider_error")
            return message

        text = getattr(response, "output_text", "").strip()
        if not text:
            message = self._fallback.synthesize(query, contexts)
            self.last_trace = self._fallback_trace(prompt, contexts, start, "empty_response")
            return message
        if self._looks_like_prompt_echo(text):
            message = self._fallback.synthesize(query, contexts)
            self.last_trace = self._fallback_trace(prompt, contexts, start, "prompt_echo")
            return message
        self.last_trace = {
            "provider": self.provider_name,
            "model": self._trace_model_name(),
            "fallback_used": False,
            "fallback_reason": None,
            "prompt": prompt,
            "approved_context": self._context_trace(contexts),
            "token_usage": self._extract_usage(response),
            "prompt_profile": self._prompts.profile,
            "prompt_version": self._prompts.version,
            "duration_ms": round((time.perf_counter() - start) * 1000),
        }
        return text

    def _trace_model_name(self) -> str:
        return settings.llm_model

    def _build_user_prompt(self, query: str, contexts: list[RetrievedKnowledge]) -> str:
        context_blocks = []
        total_chars = 0
        for index, item in enumerate(contexts, start=1):
            text = " ".join(item.text.split())
            remaining = settings.llm_context_char_limit - total_chars
            if remaining <= 0:
                break
            clipped = text[:remaining]
            total_chars += len(clipped)
            context_blocks.append(
                f"Fonte {index}: {item.source}\nTitulo: {item.title}\nTrecho oficial: {clipped}"
            )

        joined_context = "\n\n".join(context_blocks)
        return (
            f"Pergunta do cliente: {query}\n\n"
            "Contexto oficial aprovado pelo Harness:\n"
            f"{joined_context}\n\n"
            "Responda em portugues do Brasil, de forma curta, clara e apropriada para chat. "
            "Nao cite fontes, URLs, nomes de arquivos, paginas, trechos ou o contexto aprovado na conversa."
        )

    def _fallback_trace(
        self,
        prompt: str,
        contexts: list[RetrievedKnowledge],
        start: float,
        reason: str,
    ) -> dict:
        fallback_trace = getattr(self._fallback, "last_trace", {}) or {}
        return {
            "provider": self.provider_name,
            "model": self._trace_model_name(),
            "fallback_used": True,
            "fallback_reason": reason,
            "fallback_provider": fallback_trace.get("provider", "local-deterministic"),
            "prompt": prompt,
            "approved_context": self._context_trace(contexts),
            "token_usage": None,
            "prompt_profile": self._prompts.profile,
            "prompt_version": self._prompts.version,
            "duration_ms": round((time.perf_counter() - start) * 1000),
        }

    def _context_trace(self, contexts: list[RetrievedKnowledge]) -> list[dict]:
        return [
            {
                "title": item.title,
                "source": item.source,
                "score": item.score,
                "excerpt": " ".join(item.text.split())[:360],
            }
            for item in contexts
        ]

    def _extract_usage(self, response: object) -> dict | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        if isinstance(usage, dict):
            return usage
        return None

    def _looks_like_prompt_echo(self, text: str) -> bool:
        normalized = text.lower()
        blocked_terms = [
            "pergunta do cliente:",
            "contexto oficial aprovado",
            "fonte 1:",
            "fonte 2:",
            "trecho oficial:",
            "nao cite fontes",
        ]
        return any(term in normalized for term in blocked_terms)


class DockerModelRunnerGroundedFaqSynthesizer(OpenAIGroundedFaqSynthesizer):
    provider_name = "docker-model-runner"

    def _trace_model_name(self) -> str:
        return settings.docker_model_runner_model

    def synthesize(self, query: str, contexts: list[RetrievedKnowledge]) -> str:
        start = time.perf_counter()
        prompt = self._build_user_prompt(query, contexts)

        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("OpenAI-compatible SDK is not installed; using local grounded FAQ fallback.")
            message = self._fallback.synthesize(query, contexts)
            self.last_trace = self._fallback_trace(prompt, contexts, start, "missing_sdk")
            return message

        try:
            client = OpenAI(
                api_key="not-needed",
                base_url=settings.docker_model_runner_base_url,
                timeout=settings.llm_timeout_seconds,
                max_retries=0,
            )
            response = client.chat.completions.create(
                model=settings.docker_model_runner_model,
                messages=[
                    {
                        "role": "system",
                        "content": self._prompts.load("knowledge", "system"),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Docker Model Runner grounded FAQ synthesis failed; using local fallback: %s", exc)
            message = self._fallback.synthesize(query, contexts)
            self.last_trace = self._fallback_trace(prompt, contexts, start, "provider_error")
            return message

        text = (response.choices[0].message.content or "").strip()
        if not text:
            message = self._fallback.synthesize(query, contexts)
            self.last_trace = self._fallback_trace(prompt, contexts, start, "empty_response")
            return message
        if self._looks_like_prompt_echo(text):
            message = self._fallback.synthesize(query, contexts)
            self.last_trace = self._fallback_trace(prompt, contexts, start, "prompt_echo")
            return message

        self.last_trace = {
            "provider": self.provider_name,
            "model": settings.docker_model_runner_model,
            "fallback_used": False,
            "fallback_reason": None,
            "prompt": prompt,
            "approved_context": self._context_trace(contexts),
            "token_usage": self._extract_usage(response),
            "prompt_profile": self._prompts.profile,
            "prompt_version": self._prompts.version,
            "duration_ms": round((time.perf_counter() - start) * 1000),
        }
        return text


def build_grounded_faq_synthesizer() -> GroundedFaqSynthesizer | None:
    if not settings.llm_grounded_faq_enabled:
        return None

    if settings.llm_provider == "local":
        return LocalGroundedFaqSynthesizer()

    if settings.llm_provider == "openai":
        fallback: GroundedFaqSynthesizer | None = None
        if settings.llm_fallback_provider in {"docker", "docker_model_runner", "dmr"}:
            fallback = DockerModelRunnerGroundedFaqSynthesizer(
                fallback=LocalGroundedFaqSynthesizer("docker-fallback-local")
            )
        return OpenAIGroundedFaqSynthesizer(fallback=fallback)

    if settings.llm_provider in {"docker", "docker_model_runner", "dmr"}:
        return DockerModelRunnerGroundedFaqSynthesizer()

    return LocalGroundedFaqSynthesizer(provider_name=f"{settings.llm_provider}-fallback-local")
