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


def fetch_audit_events(api_url: str, customer_id: str) -> list[dict]:
    response = httpx.get(f"{api_url}/mcp/audit/{customer_id}", timeout=10.0)
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


def render_audit_panel(api_url: str, customer_id: str) -> None:
    st.subheader("Critical Audit Trail")

    try:
        events = fetch_audit_events(api_url, customer_id)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Audit lookup failed: {exc}")
        return

    st.caption("Append-only events for critical operations executed in the current mock environment.")

    if not events:
        st.info("No critical events recorded yet for this customer.")
        return

    st.metric("Critical events", len(events))

    for event in reversed(events):
        title = f"{event['event_type']} at {event['timestamp']}"
        with st.expander(title, expanded=False):
            st.json(event)


def render_last_response() -> None:
    st.subheader("Last Agent Result")
    last_result = st.session_state.get("last_result")
    if last_result is None:
        st.info("Send a message to inspect the selected route, checkpoint state, and raw response payload.")
        return

    route = last_result.get("route", "unknown")
    requires_confirmation = "Yes" if last_result.get("requires_confirmation") else "No"

    metric_left, metric_center, metric_right = st.columns(3)
    metric_left.metric("Selected route", route)
    metric_center.metric("Needs confirmation", requires_confirmation)
    metric_right.metric("Pending operation", last_result.get("pending_operation") or "-")

    st.markdown("**Response message**")
    st.write(last_result.get("message", ""))

    st.markdown("**Raw payload**")
    st.code(json.dumps(last_result, indent=2, ensure_ascii=False), language="json")


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
            st.session_state["last_result"] = result
            st.success("Message processed.")
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

    bottom_left, bottom_right = st.columns([1, 2])
    with bottom_left:
        render_audit_panel(api_url, customer_id)
    with bottom_right:
        render_last_response()


if __name__ == "__main__":
    main()
