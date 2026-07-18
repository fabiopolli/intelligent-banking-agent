from __future__ import annotations

import httpx
import streamlit as st


DEFAULT_API_URL = "http://localhost:8000/v1"
DEFAULT_SESSION_ID = "demo-session-001"
DEFAULT_CUSTOMER_ID = "123"

PROMPTS = {
    "Tarifas": "Onde consulto tarifas e pacotes de servicos?",
    "Saldo": "Qual meu saldo?",
    "Limite": "Qual meu limite?",
    "PIX": "Quero fazer um PIX de 7000 para a minha chave",
    "Emergencia": "Fui roubado",
}


def configure_page(title: str, wide: bool = True) -> None:
    st.set_page_config(page_title=title, layout="wide" if wide else "centered")
    st.markdown(
        """
        <style>
        .main .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
            max-width: 1440px;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e6e8ef;
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
            box-shadow: 0 1px 2px rgba(20, 31, 56, 0.05);
        }
        .hero-band {
            border: 1px solid #dce2ea;
            border-radius: 8px;
            padding: 1rem 1.1rem;
            background: linear-gradient(90deg, #ffffff 0%, #f6f8fb 100%);
            margin-bottom: 1rem;
        }
        .status-line {
            color: #506070;
            font-size: 0.92rem;
        }
        .source-pill {
            border: 1px solid #d9e2ec;
            border-radius: 6px;
            padding: 0.55rem 0.65rem;
            background: #fbfcfe;
            margin-bottom: 0.45rem;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.82rem;
        }
        .confirm-band {
            border: 1px solid #f0c36d;
            border-radius: 8px;
            padding: 0.8rem 0.9rem;
            background: #fff8e6;
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


def send_chat_message(api_url: str, session_id: str, customer_id: str, role: str, message: str) -> dict:
    response = httpx.post(
        f"{api_url}/channels/app/chat",
        json={
            "session_id": session_id,
            "customer_id": customer_id,
            "role": role,
            "message": message,
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_profile(api_url: str, customer_id: str) -> dict:
    response = httpx.get(f"{api_url}/mcp/users/profile/{customer_id}", timeout=10.0)
    response.raise_for_status()
    return response.json()


def fetch_balance(api_url: str, customer_id: str) -> dict:
    response = httpx.get(f"{api_url}/mcp/accounts/balance/{customer_id}", timeout=10.0)
    response.raise_for_status()
    return response.json()


def fetch_audit_events(api_url: str, customer_id: str) -> list[dict]:
    response = httpx.get(f"{api_url}/mcp/audit/{customer_id}", timeout=10.0)
    response.raise_for_status()
    return response.json()


def fetch_trace(api_url: str, session_id: str) -> dict:
    response = httpx.get(f"{api_url}/mcp/trace/{session_id}", timeout=10.0)
    response.raise_for_status()
    return response.json()


def fetch_observability_status(api_url: str) -> dict:
    response = httpx.get(f"{api_url}/mcp/observability/status", timeout=10.0)
    response.raise_for_status()
    return response.json()


def fetch_knowledge_status(api_url: str) -> dict:
    response = httpx.get(f"{api_url}/mcp/knowledge/status", timeout=10.0)
    response.raise_for_status()
    return response.json()
