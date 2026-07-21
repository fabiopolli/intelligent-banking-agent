from __future__ import annotations

import re
import unicodedata


class GuardrailsService:
    def validate_message(self, message: str) -> None:
        if not message.strip():
            raise ValueError("Message cannot be empty.")

    def contains_sensitive_credential(self, message: str) -> bool:
        normalized = "".join(
            char
            for char in unicodedata.normalize("NFKD", message.lower())
            if not unicodedata.combining(char)
        )
        sensitive_patterns = (
            r"\bsenha\b",
            r"\bitoken\b",
            r"\bcvv\b",
            r"\bcodigo de seguranca\b",
            r"\bnumero do cartao\b",
            r"\bvalidade do cartao\b",
        )
        return any(re.search(pattern, normalized) for pattern in sensitive_patterns)

    def redact_for_llm(self, message: str) -> str:
        redacted = re.sub(
            r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
            "[EMAIL_REDACTED]",
            message,
        )
        redacted = re.sub(r"(?<!\d)\+?\d{10,19}(?!\d)", "[LONG_NUMBER_REDACTED]", redacted)
        return redacted
