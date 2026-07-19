from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Protocol

from app.config import settings
from app.services.knowledge.schemas import RetrievedKnowledge

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
        secondary_sources = [item.source for item in contexts[1:]]
        source_note = ""
        if secondary_sources:
            source_note = " Tambem cruzei com outra fonte oficial recuperada."

        message = (
            "Com base nas fontes oficiais recuperadas, encontrei uma orientacao relacionada a sua pergunta. "
            f"{self._compact(primary.text)}{source_note}"
        )
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

    def __init__(self, fallback: GroundedFaqSynthesizer | None = None) -> None:
        self._fallback = fallback or LocalGroundedFaqSynthesizer("openai-fallback-local")
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
            client = OpenAI(api_key=settings.openai_api_key, timeout=settings.llm_timeout_seconds)
            response = client.responses.create(
                model=settings.llm_model,
                input=[
                    {
                        "role": "developer",
                        "content": (
                            "Voce e um sintetizador documental para atendimento bancario. "
                            "Use somente o contexto oficial aprovado recebido. "
                            "Nao invente tarifas, valores, regras, canais ou prazos. "
                            "Nao solicite nem execute ferramentas, operacoes bancarias ou side effects. "
                            "Se o contexto nao sustentar uma resposta, diga que nao ha contexto oficial suficiente."
                        ),
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
        self.last_trace = {
            "provider": self.provider_name,
            "model": settings.llm_model,
            "fallback_used": False,
            "fallback_reason": None,
            "prompt": prompt,
            "approved_context": self._context_trace(contexts),
            "token_usage": self._extract_usage(response),
            "duration_ms": round((time.perf_counter() - start) * 1000),
        }
        return text

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
            "Responda em portugues do Brasil, de forma curta, clara e apropriada para chat."
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
            "model": settings.llm_model,
            "fallback_used": True,
            "fallback_reason": reason,
            "fallback_provider": fallback_trace.get("provider", "local-deterministic"),
            "prompt": prompt,
            "approved_context": self._context_trace(contexts),
            "token_usage": None,
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


class DockerModelRunnerGroundedFaqSynthesizer(OpenAIGroundedFaqSynthesizer):
    provider_name = "docker-model-runner"

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
            )
            response = client.chat.completions.create(
                model=settings.docker_model_runner_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Voce e um sintetizador documental para atendimento bancario. "
                            "Use somente o contexto oficial aprovado recebido. "
                            "Nao invente tarifas, valores, regras, canais ou prazos. "
                            "Nao solicite nem execute ferramentas, operacoes bancarias ou side effects. "
                            "Se o contexto nao sustentar uma resposta, diga que nao ha contexto oficial suficiente."
                        ),
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

        self.last_trace = {
            "provider": self.provider_name,
            "model": settings.docker_model_runner_model,
            "fallback_used": False,
            "fallback_reason": None,
            "prompt": prompt,
            "approved_context": self._context_trace(contexts),
            "token_usage": self._extract_usage(response),
            "duration_ms": round((time.perf_counter() - start) * 1000),
        }
        return text


def build_grounded_faq_synthesizer() -> GroundedFaqSynthesizer | None:
    if not settings.llm_grounded_faq_enabled:
        return None

    if settings.llm_provider == "local":
        return LocalGroundedFaqSynthesizer()

    if settings.llm_provider == "openai":
        return OpenAIGroundedFaqSynthesizer()

    if settings.llm_provider in {"docker", "docker_model_runner", "dmr"}:
        return DockerModelRunnerGroundedFaqSynthesizer()

    return LocalGroundedFaqSynthesizer(provider_name=f"{settings.llm_provider}-fallback-local")
