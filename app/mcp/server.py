from __future__ import annotations

import httpx

from app.config import settings
from app.schemas.messages import ChatRequest
from app.services.knowledge_base import knowledge_service
from app.services.mcp_registry import mcp_tool_registry
from app.services.observability import langsmith_status
from app.security.identity import identity_service

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - startup guard
    raise RuntimeError(
        "The MCP server requires the optional 'mcp' dependency. "
        "Install project dependencies from pyproject.toml before starting it."
    ) from exc


mcp = FastMCP(
    "itau-intelligent-banking-agent",
    stateless_http=True,
    json_response=True,
    host=settings.mcp_server_host,
    port=settings.mcp_server_port,
    instructions=(
        "Agent-facing MCP server for the Itau banking-agent demo. "
        "Use resources for official knowledge and route customer requests through "
        "send_agent_message so Harness RBAC, HITL, guardrails and audit remain enforced."
    ),
)

@mcp.resource("itau://mcp/tools")
def mcp_tools() -> dict:
    """List banking tools exposed by the protected internal boundary."""

    return {"tools": mcp_tool_registry.list_tools()}


@mcp.resource("itau://knowledge/resources")
def knowledge_resources() -> dict:
    """List official knowledge resources available to the RAG layer."""

    return {"resources": mcp_tool_registry.list_resources()}


@mcp.tool()
def search_tariff_knowledge(query: str) -> dict:
    """Search official tariff, help-center and policy knowledge with grounding evidence."""

    return knowledge_service.answer_with_trace(query)


@mcp.tool()
def get_customer_profile(
    auth_token: str,
    target_customer_id: str,
) -> dict:
    """Read a customer profile after native RBAC validation."""

    return _get_profile_from_api(auth_token, target_customer_id)


def _get_profile_from_api(auth_token: str, target_customer_id: str) -> dict:
    identity_service.authenticate(auth_token, target_customer_id)
    response = httpx.get(
        f"{settings.api_internal_base_url}/mcp/users/profile/{target_customer_id}",
        headers={"X-Internal-Tool-Key": settings.internal_tool_api_key},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool()
def get_card_limit(
    auth_token: str,
    target_customer_id: str,
) -> dict:
    """Read card-limit data after native RBAC validation."""

    profile = _get_profile_from_api(auth_token, target_customer_id)
    return {
        "customer_id": profile["customer_id"],
        "name": profile["name"],
        "segment": profile["segment"],
        "card_limit": profile["card_limit"],
        "available_limit": profile["available_limit"],
        "card_status": profile["card_status"],
    }


@mcp.tool()
def get_account_balance(
    auth_token: str,
    target_customer_id: str,
) -> dict:
    """Read an account balance after native RBAC validation."""

    identity_service.authenticate(auth_token, target_customer_id)
    response = httpx.get(
        f"{settings.api_internal_base_url}/mcp/accounts/balance/{target_customer_id}",
        headers={"X-Internal-Tool-Key": settings.internal_tool_api_key},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool()
def update_card_limit(
    session_id: str,
    customer_id: str,
    new_limit: float,
    auth_token: str,
) -> dict:
    """Start the Harness-owned limit workflow; eligibility and confirmation remain mandatory."""

    return _send_to_api(
        auth_token,
        ChatRequest(
            session_id=session_id,
            customer_id=customer_id,
            message=f"Quero aumentar o limite do meu cartao para R$ {new_limit:.2f}",
        ),
    )


@mcp.tool()
def create_pix(
    session_id: str,
    customer_id: str,
    amount: float,
    destination_key: str,
    auth_token: str,
) -> dict:
    """Start the Harness-owned Pix workflow with policy checks and HITL when required."""

    return _send_to_api(
        auth_token,
        ChatRequest(
            session_id=session_id,
            customer_id=customer_id,
            message=f"Quero fazer um Pix de R$ {amount:.2f} para a chave {destination_key}",
        ),
    )


@mcp.tool()
def send_agent_message(
    auth_token: str,
    session_id: str,
    customer_id: str,
    message: str,
) -> dict:
    """Send a customer turn through the Agent Harness with RBAC, HITL and audit controls."""

    payload = ChatRequest(
        session_id=session_id,
        customer_id=customer_id,
        message=message,
    )
    return _send_to_api(auth_token, payload)


def _send_to_api(auth_token: str, payload: ChatRequest) -> dict:
    identity_service.authenticate(auth_token, payload.customer_id)
    response = httpx.post(
        f"{settings.api_internal_base_url}/channels/app/chat",
        headers={"X-Demo-Auth-Token": auth_token},
        json=payload.model_dump(),
        timeout=settings.llm_timeout_seconds + 5,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool()
def get_demo_status() -> dict:
    """Return demo readiness signals for knowledge, observability, tools and resources."""

    return {
        "knowledge": knowledge_service.status(),
        "observability": {"langsmith": langsmith_status()},
        "tools": mcp_tool_registry.list_tools(),
        "resources": mcp_tool_registry.list_resources(),
    }


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
