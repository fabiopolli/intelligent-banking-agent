from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Protocol

from app.config import settings
from app.services.knowledge.schemas import RetrievedKnowledge

logger = logging.getLogger(__name__)


class GroundedFaqSynthesizer(Protocol):
    provider_name: str

    def synthesize(self, query: str, contexts: list[RetrievedKnowledge]) -> str:
        """Return a customer-facing answer using only approved retrieved contexts."""


@dataclass
class LocalGroundedFaqSynthesizer:
    provider_name: str = "local-deterministic"

    def synthesize(self, query: str, contexts: list[RetrievedKnowledge]) -> str:
        primary = contexts[0]
        secondary_sources = [item.source for item in contexts[1:]]
        source_note = ""
        if secondary_sources:
            source_note = " Tambem cruzei com outra fonte oficial recuperada."

        return (
            "Com base nas fontes oficiais recuperadas, encontrei uma orientacao relacionada a sua pergunta. "
            f"{self._compact(primary.text)}{source_note}"
        )

    def _compact(self, text: str, limit: int = 260) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return f"{compact[:limit].rstrip()}..."


class OpenAIGroundedFaqSynthesizer:
    provider_name = "openai-responses"

    def __init__(self, fallback: GroundedFaqSynthesizer | None = None) -> None:
        self._fallback = fallback or LocalGroundedFaqSynthesizer("openai-fallback-local")

    def synthesize(self, query: str, contexts: list[RetrievedKnowledge]) -> str:
        if not settings.openai_api_key:
            return self._fallback.synthesize(query, contexts)

        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("OpenAI SDK is not installed; using local grounded FAQ fallback.")
            return self._fallback.synthesize(query, contexts)

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
                        "content": self._build_user_prompt(query, contexts),
                    },
                ],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("OpenAI grounded FAQ synthesis failed; using local fallback: %s", exc)
            return self._fallback.synthesize(query, contexts)

        text = getattr(response, "output_text", "").strip()
        if not text:
            return self._fallback.synthesize(query, contexts)
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


def build_grounded_faq_synthesizer() -> GroundedFaqSynthesizer | None:
    if not settings.llm_grounded_faq_enabled:
        return None

    if settings.llm_provider == "local":
        return LocalGroundedFaqSynthesizer()

    if settings.llm_provider == "openai":
        return OpenAIGroundedFaqSynthesizer()

    return LocalGroundedFaqSynthesizer(provider_name=f"{settings.llm_provider}-fallback-local")
