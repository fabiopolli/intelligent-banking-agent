from __future__ import annotations

import httpx

from app.config import settings
from app.schemas.messages import ChatRequest
from app.schemas.outbound import CardLimitUpdateRequest, CardUnlockRequest, PixCreateRequest
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
def search_tariff_knowledge(
    query: str,
    llm_provider: str = "configured",
) -> dict:
    """Search official tariff, help-center and policy knowledge with grounding evidence."""

    if llm_provider not in {"configured", "docker_model_runner"}:
        raise ValueError("Unsupported LLM provider override.")
    return knowledge_service.answer_with_trace(query, llm_provider=llm_provider)


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
        "credit_score": profile["credit_score"],
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
    target_customer_id: str,
    new_limit: float,
    auth_token: str,
) -> dict:
    """Execute a limit mutation already authorized and confirmed by the Agent Harness."""

    identity_service.authenticate(auth_token, target_customer_id)
    response = httpx.post(
        f"{settings.api_internal_base_url}/mcp/cards/limit",
        headers={"X-Internal-Tool-Key": settings.internal_tool_api_key},
        json=CardLimitUpdateRequest(
            customer_id=target_customer_id,
            new_limit=new_limit,
        ).model_dump(),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool()
def unlock_card(
    target_customer_id: str,
    auth_token: str,
) -> dict:
    """Unlock a card after admin RBAC and HITL were completed by the Agent Harness."""

    principal = identity_service.authenticate(auth_token, target_customer_id)
    if principal.role != "admin" or "customer:any:write" not in principal.scopes:
        raise PermissionError("Administrator write scope is required for card unlock.")
    response = httpx.post(
        f"{settings.api_internal_base_url}/mcp/cards/unlock",
        headers={"X-Internal-Tool-Key": settings.internal_tool_api_key},
        json=CardUnlockRequest(customer_id=target_customer_id).model_dump(),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool()
def create_pix(
    target_customer_id: str,
    amount: float,
    destination_key: str,
    auth_token: str,
) -> dict:
    """Execute a Pix mutation already authorized and confirmed by the Agent Harness."""

    identity_service.authenticate(auth_token, target_customer_id)
    response = httpx.post(
        f"{settings.api_internal_base_url}/mcp/payments/pix",
        headers={"X-Internal-Tool-Key": settings.internal_tool_api_key},
        json=PixCreateRequest(
            customer_id=target_customer_id,
            amount=amount,
            destination_key=destination_key,
        ).model_dump(),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


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
