from __future__ import annotations


class IntentRouter:
    def classify_confident(self, message: str) -> str | None:
        """Return a native route only when the banking intent is explicit."""
        normalized = message.lower()

        if any(term in normalized for term in ("roubado", "assalto", "fraude", "perdi")):
            return "emergency"
        if "saldo" in normalized:
            return "core_banking_balance"
        if "limite" in normalized and any(
            term in normalized for term in ("meu limite", "meu cart", "aument", "consult")
        ):
            return "core_banking_limit"
        if "pix" in normalized and any(
            term in normalized for term in ("fazer", "faça", "faca", "enviar", "transferir")
        ):
            return "transaction"
        return None

    def classify(self, message: str) -> str:
        confident_route = self.classify_confident(message)
        if confident_route is not None:
            return confident_route
        normalized = message.lower()
        if "limite" in normalized:
            return "core_banking_limit"
        if "pix" in normalized:
            return "transaction"
        return "faq_fast_path"
