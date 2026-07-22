from __future__ import annotations

import re


class TargetCustomerResolver:
    _EXPLICIT_CUSTOMER_PATTERN = re.compile(
        r"\b(?:cliente|conta|customer)\s*(?:id\s*)?[#:-]?\s*(\d{3,})\b",
        re.IGNORECASE,
    )

    def resolve(self, message: str, default_customer_id: str) -> str:
        match = self._EXPLICIT_CUSTOMER_PATTERN.search(message)
        if match is None:
            return default_customer_id
        return match.group(1)

    def remove_reference(self, message: str) -> str:
        return self._EXPLICIT_CUSTOMER_PATTERN.sub("", message, count=1).strip()


target_customer_resolver = TargetCustomerResolver()
