from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import settings


def require_internal_tool_key(x_internal_tool_key: str | None = Header(default=None)) -> None:
    if x_internal_tool_key != settings.internal_tool_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal tool API key is required for MCP-style tool endpoints.",
        )
