from __future__ import annotations

import os

import httpx
import streamlit as st


DEFAULT_API_URL = os.getenv("DEFAULT_API_URL", "http://localhost:8000/v1")
DEFAULT_SESSION_ID = "demo-session-001"
DEFAULT_CUSTOMER_ID = "123"
DEFAULT_INTERNAL_TOOL_KEY = os.getenv("INTERNAL_TOOL_API_KEY", "demo-internal-tool-key")
DEFAULT_DEMO_AUTH_TOKEN = os.getenv("DEMO_AUTH_TOKEN", "demo-customer-123-token")
DEMO_CUSTOMER_TOKEN = os.getenv("DEMO_CUSTOMER_TOKEN", DEFAULT_DEMO_AUTH_TOKEN)
DEMO_MANAGER_TOKEN = os.getenv("DEMO_MANAGER_TOKEN", "demo-manager-token")
DEMO_ADMIN_TOKEN = os.getenv("DEMO_ADMIN_TOKEN", "demo-admin-token")

PROMPTS = {
    "Tarifas": "Onde consulto tarifas e pacotes de servicos?",
    "Saldo": "Qual meu saldo?",
    "Limite": "Quero aumentar o limite do meu cartao para R$ 15.000",
    "PIX": "Quero fazer um PIX de 7000 para chave pix maria@example.com",
    "Emergencia": "Fui roubado",
}


def configure_page(title: str, wide: bool = True) -> None:
    st.set_page_config(page_title=title, layout="wide" if wide else "centered")
    st.markdown(
        """
        <style>
        .stApp {
            background: #0f141c;
            color: #eef3f8;
        }
        .main .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
            max-width: 1440px;
        }
        section[data-testid="stSidebar"] {
            background: #111721;
            border-right: 1px solid #303846;
        }
        section[data-testid="stSidebar"] * {
            color: #eef3f8 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"],
        div[data-testid="stExpander"],
        div[data-testid="stAlert"],
        div[data-testid="stChatMessage"],
        div[data-testid="stForm"],
        div[data-testid="stCodeBlock"] {
            background-color: #141922 !important;
            border-color: #303846 !important;
            color: #eef3f8 !important;
        }
        div[data-testid="stAlert"] {
            border-radius: 8px;
        }
        div[data-testid="stMetric"] {
            background: #141922;
            border: 1px solid #303846;
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.18);
        }
        div[data-testid="stMetric"] label,
        div[data-testid="stMetric"] [data-testid="stMetricLabel"],
        div[data-testid="stMetric"] [data-testid="stMetricValue"],
        div[data-testid="stMetric"] [data-testid="stMetricDelta"],
        div[data-testid="stMetric"] * {
            color: #f3f7fb !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 1.05rem !important;
            line-height: 1.2 !important;
            white-space: normal !important;
            overflow-wrap: anywhere !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] div {
            overflow: visible !important;
            text-overflow: clip !important;
            white-space: normal !important;
        }
        div[data-testid="stMetric"] [data-testid="stMetricLabel"] {
            font-size: 0.78rem !important;
            white-space: normal !important;
            overflow-wrap: anywhere !important;
        }
        div[data-baseweb="input"],
        div[data-baseweb="textarea"],
        div[data-baseweb="select"] > div {
            background-color: #111721 !important;
            border-color: #3b4658 !important;
            color: #f3f7fb !important;
        }
        input,
        textarea,
        [contenteditable="true"] {
            color: #f3f7fb !important;
            caret-color: #f3f7fb !important;
        }
        button[kind],
        div[data-testid="stButton"] button,
        div[data-testid="stFormSubmitButton"] button {
            border-radius: 8px;
            border-color: #3b4658;
        }
        div[data-testid="stMarkdownContainer"],
        div[data-testid="stCaptionContainer"],
        p,
        span,
        label {
            color: #eef3f8;
        }
        .hero-band {
            border: 1px solid #303846;
            border-radius: 8px;
            padding: 1rem 1.1rem;
            background: #141922;
            margin-bottom: 1rem;
        }
        .hero-band h2 {
            color: #f7fafc !important;
        }
        .status-line {
            color: #c7d0dc;
            font-size: 0.92rem;
        }
        .source-pill {
            border: 1px solid #3b4658;
            border-radius: 6px;
            padding: 0.55rem 0.65rem;
            background: #111721;
            color: #f3f7fb;
            margin-bottom: 0.45rem;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.82rem;
        }
        .confirm-band {
            border: 1px solid #d9982f;
            border-radius: 8px;
            padding: 0.8rem 0.9rem;
            background: #2b2110;
            color: #fff6df;
            margin-top: 0.8rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str, caption: str) -> None:
    st.markdown(
        f"""
        <div class="hero-band">
            <h2 style="margin:0;color:#101828;">{title}</h2>
            <div class="status-line">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def authenticate_demo_identity(api_url: str, auth_token: str) -> dict:
    response = httpx.get(
        f"{api_url}/auth/demo/session",
        headers={"X-Demo-Auth-Token": auth_token},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def send_chat_message(
    api_url: str,
    session_id: str,
    customer_id: str,
    auth_token: str,
    message: str,
) -> dict:
    response = httpx.post(
        f"{api_url}/channels/app/chat",
        headers={"X-Demo-Auth-Token": auth_token},
        json={
            "session_id": session_id,
            "customer_id": customer_id,
            "message": message,
        },
        timeout=httpx.Timeout(CHAT_REQUEST_TIMEOUT_SECONDS, connect=3.0),
    )
    if response.status_code == 403:
        return {
            "route": "authorization_denied",
            "session_id": session_id,
            "message": (
                "Por seguranca, voce nao tem autorizacao para consultar ou movimentar esta conta. "
                "Confira o cliente selecionado ou entre com um perfil autorizado."
            ),
            "observability": {"authorization": {"allowed": False}},
        }
    response.raise_for_status()
    return response.json()


def fetch_profile(api_url: str, customer_id: str) -> dict:
    response = httpx.get(
        f"{api_url}/mcp/users/profile/{customer_id}",
        headers=_internal_tool_headers(),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_balance(api_url: str, customer_id: str) -> dict:
    response = httpx.get(
        f"{api_url}/mcp/accounts/balance/{customer_id}",
        headers=_internal_tool_headers(),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_audit_events(api_url: str, customer_id: str) -> list[dict]:
    response = httpx.get(
        f"{api_url}/mcp/audit/{customer_id}",
        headers=_internal_tool_headers(),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_trace(api_url: str, session_id: str) -> dict:
    response = httpx.get(
        f"{api_url}/mcp/trace/{session_id}",
        headers=_internal_tool_headers(),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_observability_status(api_url: str) -> dict:
    response = httpx.get(
        f"{api_url}/mcp/observability/status",
        headers=_internal_tool_headers(),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_knowledge_status(api_url: str) -> dict:
    response = httpx.get(
        f"{api_url}/mcp/knowledge/status",
        headers=_internal_tool_headers(),
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_mcp_tools(api_url: str) -> dict:
    response = httpx.get(f"{api_url}/mcp/tools", headers=_internal_tool_headers(), timeout=10.0)
    response.raise_for_status()
    return response.json()


def fetch_mcp_resources(api_url: str) -> dict:
    response = httpx.get(f"{api_url}/mcp/resources", headers=_internal_tool_headers(), timeout=10.0)
    response.raise_for_status()
    return response.json()


def _internal_tool_headers() -> dict[str, str]:
    return {"X-Internal-Tool-Key": DEFAULT_INTERNAL_TOOL_KEY}
CHAT_REQUEST_TIMEOUT_SECONDS = 30.0
