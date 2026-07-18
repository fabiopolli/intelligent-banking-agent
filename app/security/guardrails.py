from __future__ import annotations


class GuardrailsService:
    def validate_message(self, message: str) -> None:
        if not message.strip():
            raise ValueError("Message cannot be empty.")
