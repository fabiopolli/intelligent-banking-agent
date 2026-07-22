from __future__ import annotations


class IntentRouter:
    def classify(self, message: str) -> str:
        normalized = message.lower()

        if any(term in normalized for term in ("roubado", "assalto", "fraude", "perdi")):
            return "emergency"
        if "limite" in normalized:
            return "core_banking_limit"
        if "saldo" in normalized:
            return "core_banking_balance"
        if "pix" in normalized:
            return "transaction"
        return "faq_fast_path"
