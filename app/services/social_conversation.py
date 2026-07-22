from __future__ import annotations

import re
import unicodedata


class SocialConversationService:
    _BANKING_TERMS = {
        "saldo",
        "limite",
        "pix",
        "cartao",
        "tarifa",
        "taxa",
        "saque",
        "ted",
        "investimento",
        "consignado",
        "emprestimo",
        "bloquear",
        "roubado",
        "fraude",
    }

    def answer(self, message: str) -> str | None:
        normalized = self._normalize(message)
        tokens = set(normalized.split())
        if tokens & self._BANKING_TERMS:
            return None

        name = self._extract_name(message)
        if self._is_greeting(normalized) or name:
            greeting = f"Olá, {name}!" if name else "Olá!"
            return (
                f"{greeting} Que bom falar com você. Posso ajudar com saldo, limite, Pix, cartão, "
                "tarifas, investimentos ou consignado. Como posso ajudar?"
            )
        if self._is_thanks(normalized):
            return "Por nada! Fico à disposição se precisar de mais alguma coisa."
        if self._is_farewell(normalized):
            return "Até mais! Quando precisar, estarei por aqui para ajudar."
        return None

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value.lower())
        ascii_text = "".join(character for character in normalized if not unicodedata.combining(character))
        return re.sub(r"[^a-z0-9 ]+", " ", ascii_text).strip()

    @staticmethod
    def _extract_name(message: str) -> str | None:
        match = re.search(
            r"\b(?:meu nome [ée]|me chamo)\s+([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ' -]{0,39})",
            message,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        name = re.split(r"[,.!?]", match.group(1), maxsplit=1)[0].strip()
        return " ".join(part.capitalize() for part in name.split()) or None

    @staticmethod
    def _is_greeting(message: str) -> bool:
        return bool(re.fullmatch(r"(?:ola|oi|bom dia|boa tarde|boa noite)(?: tudo bem)?", message))

    @staticmethod
    def _is_thanks(message: str) -> bool:
        return bool(re.fullmatch(r"(?:obrigad[oa]|muito obrigad[oa]|valeu)(?: mesmo)?", message))

    @staticmethod
    def _is_farewell(message: str) -> bool:
        return bool(re.fullmatch(r"(?:tchau|ate mais|ate logo|falou)", message))


social_conversation_service = SocialConversationService()
