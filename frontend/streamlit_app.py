from __future__ import annotations

import json
import time

import httpx
import streamlit as st


DEFAULT_API_URL = "http://localhost:8000/v1"

PROMPTS = {
    "RAG tarifas": "Onde consulto tarifas e pacotes de servicos?",
    "RAG sem contexto": "Qual e a cotacao do dolar comercial agora?",
    "Saldo": "Qual meu saldo?",
    "Limite": "Qual meu limite?",
    "PIX": "Quero fazer um PIX de 7000 para a minha chave",
    "Emergencia": "Fui roubado",
}


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


def configure_page() -> None:
    st.set_page_config(page_title="Intelligent Banking Agent Demo", layout="wide")
    st.markdown(
        """
        <style>
        .main .block-container {
            padding-top: 1.5rem;
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
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session_state() -> None:
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("last_result", None)
    st.session_state.setdefault("selected_prompt", PROMPTS["RAG tarifas"])
    st.session_state.setdefault("profile", None)
    st.session_state.setdefault("balance", None)
    st.session_state.setdefault("audit_events", [])
    st.session_state.setdefault("last_latency_ms", None)


def render_header() -> None:
    st.markdown(
        """
        <div class="hero-band">
            <h2 style="margin:0;color:#101828;">Itau Intelligent Banking Agent</h2>
            <div class="status-line">
                Demo local com Harness, RBAC, HITL, RAG grounded, estado mutavel e auditoria critica.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> tuple[str, str, str, str]:
    st.sidebar.header("Session")
    api_url = st.sidebar.text_input("API URL", value=DEFAULT_API_URL)
    session_id = st.sidebar.text_input("Session ID", value="demo-session-001")
    customer_id = st.sidebar.text_input("Customer ID", value="123")
    role = st.sidebar.selectbox("Role", options=["customer", "manager", "admin"], index=0)
    return api_url, session_id, customer_id, role


def refresh_snapshot(api_url: str, customer_id: str) -> None:
    st.session_state["profile"] = fetch_profile(api_url, customer_id)
    st.session_state["balance"] = fetch_balance(api_url, customer_id)
    st.session_state["audit_events"] = fetch_audit_events(api_url, customer_id)


def render_snapshot(api_url: str, customer_id: str) -> None:
    st.subheader("Customer")

    if st.session_state.get("profile") is None or st.session_state.get("balance") is None:
        try:
            refresh_snapshot(api_url, customer_id)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Snapshot failed: {exc}")
            return

    profile = st.session_state["profile"]
    balance = st.session_state["balance"]

    top_left, top_right = st.columns(2)
    top_left.metric("Balance", f"R$ {float(balance['balance']):,.2f}")
    top_right.metric("Card limit", f"R$ {float(profile['card_limit']):,.2f}")

    lower_left, lower_right = st.columns(2)
    lower_left.metric("Card", profile["card_status"])
    lower_right.metric("Segment", profile["segment"])

    if st.button("Refresh state"):
        try:
            refresh_snapshot(api_url, customer_id)
            st.success("State refreshed.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Refresh failed: {exc}")


def render_prompt_buttons() -> None:
    st.caption("Use cases")
    prompt_items = list(PROMPTS.items())
    for row_start in range(0, len(prompt_items), 3):
        columns = st.columns(3)
        for column, (label, prompt) in zip(columns, prompt_items[row_start : row_start + 3]):
            if column.button(label, use_container_width=True):
                st.session_state["selected_prompt"] = prompt


def render_chat_console(api_url: str, session_id: str, customer_id: str, role: str) -> None:
    st.subheader("Agent Console")
    render_prompt_buttons()

    for item in st.session_state["chat_history"]:
        with st.chat_message(item["role"]):
            st.write(item["content"])

    with st.form("chat_form", clear_on_submit=False):
        message = st.text_area("Message", value=st.session_state["selected_prompt"], height=110)
        submitted = st.form_submit_button("Send message", type="primary", use_container_width=True)

    if not submitted:
        return

    st.session_state["chat_history"].append({"role": "user", "content": message})
    try:
        start = time.perf_counter()
        result = send_chat_message(api_url, session_id, customer_id, role, message)
        st.session_state["last_latency_ms"] = round((time.perf_counter() - start) * 1000)
        st.session_state["last_result"] = result
        st.session_state["chat_history"].append({"role": "assistant", "content": result.get("message", "")})
        if result.get("route") in {"transaction", "emergency"}:
            refresh_snapshot(api_url, customer_id)
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Message failed: {exc}")


def render_trace_panel() -> None:
    st.subheader("Harness Trace")
    last_result = st.session_state.get("last_result")
    if last_result is None:
        st.info("Send a message to inspect routing, HITL, grounding, and latency.")
        return

    route = last_result.get("route", "unknown")
    requires_confirmation = "Yes" if last_result.get("requires_confirmation") else "No"
    source_count = len(last_result.get("grounding_sources") or [])
    latency = st.session_state.get("last_latency_ms")

    first, second = st.columns(2)
    first.metric("Route", route)
    second.metric("Latency", f"{latency} ms" if latency is not None else "-")

    third, fourth = st.columns(2)
    third.metric("HITL", requires_confirmation)
    fourth.metric("Sources", source_count)

    pending_operation = last_result.get("pending_operation")
    if pending_operation:
        st.warning(f"Checkpoint pending: {pending_operation}")
    elif route == "emergency":
        st.error("Emergency path executed with critical audit trail.")
    elif route == "faq_fast_path" and source_count > 0:
        st.success("Grounded answer returned with official source metadata.")
    elif route == "faq_fast_path":
        st.warning("Safe fail: no sufficient official context was returned.")
    else:
        st.info("Operational path completed.")


def render_grounding_panel(last_result: dict | None = None) -> None:
    result = last_result or st.session_state.get("last_result")
    st.subheader("Evidence")
    if result is None or result.get("route") != "faq_fast_path":
        st.info("RAG evidence appears here for documental questions.")
        return

    sources = result.get("grounding_sources") or []
    st.metric("Official sources", len(sources))

    if not sources:
        st.warning("No official grounding source was returned for this answer.")
        return

    for source in sources:
        st.markdown(f"<div class='source-pill'>{source}</div>", unsafe_allow_html=True)


def render_audit_panel() -> None:
    st.subheader("Critical Audit")
    events = st.session_state.get("audit_events") or []

    if not events:
        st.info("No critical events recorded yet for this customer.")
        return

    st.metric("Events", len(events))
    for event in reversed(events[-5:]):
        title = f"{event['event_type']} | {event['timestamp']}"
        with st.expander(title, expanded=False):
            st.json(event)


def render_payload_panel() -> None:
    last_result = st.session_state.get("last_result")
    with st.expander("Technical payload", expanded=False):
        if last_result is None:
            st.write("No payload yet.")
            return
        st.code(json.dumps(last_result, indent=2, ensure_ascii=False), language="json")


def main() -> None:
    configure_page()
    init_session_state()
    render_header()

    api_url, session_id, customer_id, role = render_sidebar()

    left, center, right = st.columns([1.05, 1.7, 1.05])
    with left:
        render_snapshot(api_url, customer_id)
        render_audit_panel()
    with center:
        render_chat_console(api_url, session_id, customer_id, role)
    with right:
        render_trace_panel()
        render_grounding_panel()
        render_payload_panel()


if __name__ == "__main__":
    main()
