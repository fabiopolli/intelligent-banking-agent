from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator


_AUTH_TOKEN: ContextVar[str | None] = ContextVar("trusted_request_auth_token", default=None)


@contextmanager
def trusted_auth_token_scope(token: str | None) -> Iterator[None]:
    context_token = _AUTH_TOKEN.set(token)
    try:
        yield
    finally:
        _AUTH_TOKEN.reset(context_token)


def current_trusted_auth_token() -> str:
    token = _AUTH_TOKEN.get()
    if not token:
        raise PermissionError("Trusted request credential is unavailable for the MCP tool call.")
    return token
