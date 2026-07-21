from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def run_smoke(url: str) -> dict[str, Any]:
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            resources = await session.list_resources()
            status = await session.call_tool("get_demo_status", {})

    tool_names = [tool.name for tool in tools.tools]
    resource_uris = [str(resource.uri) for resource in resources.resources]
    status_text = status.content[0].text if status.content else "{}"
    status_payload = json.loads(status_text)

    assert "send_agent_message" in tool_names
    assert "search_tariff_knowledge" in tool_names
    assert "get_demo_status" in tool_names
    assert "get_customer_profile" in tool_names
    assert "get_card_limit" in tool_names
    assert "update_card_limit" in tool_names
    assert "create_pix" in tool_names
    assert "itau://mcp/tools" in resource_uris
    assert "itau://knowledge/resources" in resource_uris
    assert status_payload["knowledge"]["pdf_ingested"] is True
    assert any(tool["name"] == "create_pix" and tool["requires_hitl"] for tool in status_payload["tools"])

    return {
        "tools": tool_names,
        "resources": resource_uris,
        "pdf_ingested": status_payload["knowledge"]["pdf_ingested"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test the Itau MCP Streamable HTTP server.")
    parser.add_argument("--url", default="http://127.0.0.1:8600/mcp")
    args = parser.parse_args()

    result = asyncio.run(run_smoke(args.url))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
