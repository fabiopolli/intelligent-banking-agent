from __future__ import annotations

from app.config import settings
from app.schemas.messages import ChatRequest
from app.services.harness import DemoHarness
from app.services.knowledge_base import knowledge_service
from app.services.mcp_registry import mcp_tool_registry
from app.services.observability import langsmith_status

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

_harness = DemoHarness()


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
def send_agent_message(
    session_id: str,
    customer_id: str,
    message: str,
    role: str = "customer",
) -> dict:
    """Send a customer turn through the Agent Harness with RBAC, HITL and audit controls."""

    payload = ChatRequest(
        session_id=session_id,
        customer_id=customer_id,
        message=message,
        role=role,
    )
    return _harness.handle_message(payload)


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
