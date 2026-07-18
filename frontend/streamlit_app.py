from __future__ import annotations

import json

import httpx
import streamlit as st


DEFAULT_API_URL = "http://localhost:8000/v1"


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


def render_sidebar() -> tuple[str, str, str, str]:
    st.sidebar.header("Session")
    api_url = st.sidebar.text_input("API URL", value=DEFAULT_API_URL)
    session_id = st.sidebar.text_input("Session ID", value="demo-session-001")
    customer_id = st.sidebar.text_input("Customer ID", value="123")
    role = st.sidebar.selectbox("Role", options=["customer", "manager", "admin"], index=0)
    return api_url, session_id, customer_id, role


def render_snapshot(api_url: str, customer_id: str) -> None:
    st.subheader("Customer Snapshot")
    left, right = st.columns(2)

    try:
        profile = fetch_profile(api_url, customer_id)
        left.json(profile)
    except Exception as exc:  # noqa: BLE001
        left.error(f"Profile lookup failed: {exc}")

    try:
        balance = fetch_balance(api_url, customer_id)
        right.json(balance)
    except Exception as exc:  # noqa: BLE001
        right.error(f"Balance lookup failed: {exc}")


def render_chat_console(api_url: str, session_id: str, customer_id: str, role: str) -> None:
    st.subheader("Agent Console")

    quick_prompts = {
        "Fast path": "Como funciona a tarifa da conta?",
        "Saldo": "Qual meu saldo?",
        "Limite": "Qual meu limite?",
        "PIX": "Quero fazer um PIX",
        "Emergencia": "Fui roubado",
    }

    selected_label = st.selectbox("Quick prompt", options=list(quick_prompts.keys()), index=0)
    default_message = quick_prompts[selected_label]
    message = st.text_area("Message", value=default_message, height=120)

    if st.button("Send message", type="primary"):
        try:
            result = send_chat_message(api_url, session_id, customer_id, role, message)
            st.success("Message processed.")

            route = result.get("route", "unknown")
            st.metric("Selected route", route)

            st.markdown("**Response message**")
            st.write(result.get("message", ""))

            st.markdown("**Raw payload**")
            st.code(json.dumps(result, indent=2, ensure_ascii=False), language="json")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Message failed: {exc}")


def main() -> None:
    st.set_page_config(page_title="Intelligent Banking Agent Demo", layout="wide")
    st.title("Intelligent Banking Agent")
    st.caption("Frontend slice 0 for local validation of routing, session state, and stateful mocks.")

    api_url, session_id, customer_id, role = render_sidebar()

    top_left, top_right = st.columns([1, 2])
    with top_left:
        render_snapshot(api_url, customer_id)
    with top_right:
        render_chat_console(api_url, session_id, customer_id, role)


if __name__ == "__main__":
    main()
