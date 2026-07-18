from __future__ import annotations

import os
from collections.abc import Callable
from typing import ParamSpec, TypeVar


P = ParamSpec("P")
T = TypeVar("T")

try:
    from langsmith import traceable as _langsmith_traceable
except ImportError:  # pragma: no cover - fallback for minimal local environments
    _langsmith_traceable = None


def traceable(name: str, run_type: str = "chain") -> Callable[[Callable[P, T]], Callable[P, T]]:
    if _langsmith_traceable is None:
        return lambda wrapped: wrapped
    return _langsmith_traceable(name=name, run_type=run_type)


def langsmith_status() -> dict[str, str | bool | None]:
    tracing_enabled = os.getenv("LANGSMITH_TRACING") == "true" or os.getenv("LANGCHAIN_TRACING_V2") == "true"
    return {
        "available": _langsmith_traceable is not None,
        "enabled": tracing_enabled,
        "project": os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT"),
        "endpoint": os.getenv("LANGSMITH_ENDPOINT") or "https://api.smith.langchain.com",
    }
