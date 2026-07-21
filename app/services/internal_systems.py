from __future__ import annotations

import asyncio
import json
import time
from typing import Protocol

from app.config import settings
from app.schemas.outbound import BalanceResponse, CustomerProfileResponse
from app.security.request_credentials import current_trusted_auth_token
from app.services.mock_bank import mock_bank_service


class InternalSystemsGateway(Protocol):
    last_trace: dict

    def get_customer_profile(self, customer_id: str) -> CustomerProfileResponse | None: ...

    def get_card_limit(self, customer_id: str) -> CustomerProfileResponse | None: ...

    def get_account_balance(self, customer_id: str) -> BalanceResponse | None: ...


class InternalSystemsUnavailable(RuntimeError):
    pass


class LocalInternalSystemsGateway:
    def __init__(self) -> None:
        self.last_trace: dict = {}

    def get_customer_profile(self, customer_id: str) -> CustomerProfileResponse | None:
        started_at = time.perf_counter()
        result = mock_bank_service.get_customer_profile(customer_id)
        self.last_trace = self._trace("get_customer_profile", started_at)
        return result

    def get_account_balance(self, customer_id: str) -> BalanceResponse | None:
        started_at = time.perf_counter()
        result = mock_bank_service.get_balance(customer_id)
        self.last_trace = self._trace("get_account_balance", started_at)
        return result

    def get_card_limit(self, customer_id: str) -> CustomerProfileResponse | None:
        started_at = time.perf_counter()
        result = mock_bank_service.get_customer_profile(customer_id)
        self.last_trace = self._trace("get_card_limit", started_at)
        return result

    @staticmethod
    def _trace(tool: str, started_at: float) -> dict:
        return {
            "tool": tool,
            "transport": "local-adapter",
            "status": "success",
            "duration_ms": round((time.perf_counter() - started_at) * 1000),
        }


class McpInternalSystemsGateway:
    def __init__(self, url: str | None = None) -> None:
        self._url = url or settings.mcp_client_url
        self.last_trace: dict = {}

    def get_customer_profile(self, customer_id: str) -> CustomerProfileResponse | None:
        payload = self._call_tool(
            "get_customer_profile",
            {"auth_token": current_trusted_auth_token(), "target_customer_id": customer_id},
        )
        return CustomerProfileResponse.model_validate(payload)

    def get_account_balance(self, customer_id: str) -> BalanceResponse | None:
        payload = self._call_tool(
            "get_account_balance",
            {"auth_token": current_trusted_auth_token(), "target_customer_id": customer_id},
        )
        return BalanceResponse.model_validate(payload)

    def get_card_limit(self, customer_id: str) -> CustomerProfileResponse | None:
        payload = self._call_tool(
            "get_card_limit",
            {"auth_token": current_trusted_auth_token(), "target_customer_id": customer_id},
        )
        return CustomerProfileResponse.model_validate(payload)

    def _call_tool(self, tool: str, arguments: dict) -> dict:
        started_at = time.perf_counter()
        try:
            payload = asyncio.run(self._call_tool_async(tool, arguments))
        except Exception as exc:
            self.last_trace = {
                "tool": tool,
                "transport": "mcp-streamable-http",
                "status": "failed",
                "error_type": type(exc).__name__,
                "duration_ms": round((time.perf_counter() - started_at) * 1000),
            }
            raise InternalSystemsUnavailable(f"MCP internal-system tool failed: {tool}") from exc
        self.last_trace = {
            "tool": tool,
            "transport": "mcp-streamable-http",
            "status": "success",
            "duration_ms": round((time.perf_counter() - started_at) * 1000),
        }
        return payload

    async def _call_tool_async(self, tool: str, arguments: dict) -> dict:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(self._url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments)
        if result.isError:
            raise RuntimeError(f"MCP tool returned an error: {tool}")
        if result.structuredContent:
            return dict(result.structuredContent)
        text = result.content[0].text if result.content else "{}"
        return json.loads(text)


def build_internal_systems_gateway() -> InternalSystemsGateway:
    if settings.internal_systems_transport.lower() == "mcp":
        return McpInternalSystemsGateway()
    return LocalInternalSystemsGateway()
