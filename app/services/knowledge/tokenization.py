from __future__ import annotations

import re
import unicodedata

from app.services.knowledge.config import RAG_STOPWORDS


def normalize_for_match(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("ascii")


def tokenize(text: str) -> list[str]:
    normalized = normalize_for_match(text)
    return [
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if len(token) > 2 and token not in RAG_STOPWORDS
    ]
