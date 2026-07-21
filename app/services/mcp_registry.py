from __future__ import annotations


class McpToolRegistry:
    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "get_account_balance",
                "kind": "tool",
                "transport": "mcp-and-internal-rest",
                "path": "/v1/mcp/accounts/balance/{customer_id}",
                "requires_rbac": True,
                "requires_hitl": False,
                "audited": False,
                "description": "Consulta saldo pelo gateway MCP apos autorizacao nativa do Harness.",
            },
            {
                "name": "get_customer_profile",
                "kind": "tool",
                "transport": "mcp-and-internal-rest",
                "path": "/v1/mcp/users/profile/{customer_id}",
                "requires_rbac": True,
                "requires_hitl": False,
                "audited": False,
                "description": "Consulta perfil mockado do cliente para uso controlado pelo Harness.",
            },
            {
                "name": "get_card_limit",
                "kind": "tool",
                "transport": "mcp-and-internal-rest",
                "path": "/v1/mcp/users/profile/{customer_id}",
                "requires_rbac": True,
                "requires_hitl": False,
                "audited": False,
                "description": "Consulta limite de cartao dentro do perfil do cliente.",
            },
            {
                "name": "update_card_limit",
                "kind": "tool",
                "transport": "mcp-and-internal-rest",
                "path": "/v1/mcp/cards/limit",
                "requires_rbac": True,
                "requires_hitl": False,
                "audited": True,
                "description": "Atualiza limite mockado e gera auditoria LIMIT_CHANGE.",
            },
            {
                "name": "create_pix",
                "kind": "tool",
                "transport": "mcp-and-internal-rest",
                "path": "/v1/mcp/payments/pix",
                "requires_rbac": True,
                "requires_hitl": True,
                "audited": True,
                "description": "Executa PIX mockado apos preflight do Harness e HITL quando aplicavel.",
            },
            {
                "name": "block_card_emergency",
                "kind": "tool",
                "transport": "internal-rest",
                "path": "Harness-only",
                "requires_rbac": True,
                "requires_hitl": False,
                "audited": True,
                "description": "Bloqueia cartao em emergencia, com prioridade maxima e auditoria CARD_BLOCKED.",
            },
            {
                "name": "search_tariff_knowledge",
                "kind": "resource-tool",
                "transport": "internal-service",
                "path": "/v1/mcp/knowledge/status",
                "requires_rbac": False,
                "requires_hitl": False,
                "audited": False,
                "description": "Expõe metadados da base RAG oficial; o PDF permanece fonte documental ingerida.",
            },
        ]

    def list_resources(self) -> list[dict]:
        return [
            {
                "uri": "itau://knowledge/tariff-pdf",
                "name": "Tabela Geral de Tarifas PF",
                "source": ".docs/tabela_geral_de_tarifas_pf_pdf.pdf",
                "kind": "pdf-knowledge-resource",
                "description": "PDF oficial usado pelo RAG local para respostas grounded de tarifas.",
            },
            {
                "uri": "itau://knowledge/help-center",
                "name": "Central de Ajuda Itau",
                "source": "https://www.itau.com.br/atendimento-itau/para-voce",
                "kind": "official-web-snapshot",
                "description": "Snapshot oficial usado para FAQ e canais de atendimento.",
            },
            {
                "uri": "itau://knowledge/policies",
                "name": "Politicas Itau",
                "source": "https://www.itau.com.br/relacoes-com-investidores/politicas/",
                "kind": "official-web-snapshot",
                "description": "Snapshot oficial usado para governanca, integridade e politicas.",
            },
        ]


mcp_tool_registry = McpToolRegistry()
