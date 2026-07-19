from __future__ import annotations

import json

import streamlit as st

from frontend.ui_common import (
    DEFAULT_API_URL,
    DEFAULT_CUSTOMER_ID,
    DEFAULT_SESSION_ID,
    configure_page,
    fetch_audit_events,
    fetch_balance,
    fetch_knowledge_status,
    fetch_observability_status,
    fetch_profile,
    fetch_trace,
    render_header,
)


def render_sidebar() -> tuple[str, str, str]:
    st.sidebar.header("Inspector")
    api_url = st.sidebar.text_input("API URL", value=DEFAULT_API_URL)
    session_id = st.sidebar.text_input("Session ID", value=DEFAULT_SESSION_ID)
    customer_id = st.sidebar.text_input("Customer ID", value=DEFAULT_CUSTOMER_ID)
    return api_url, session_id, customer_id


def render_customer_panel(api_url: str, customer_id: str) -> None:
    st.subheader("Customer State")
    try:
        profile = fetch_profile(api_url, customer_id)
        balance = fetch_balance(api_url, customer_id)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Customer lookup failed: {exc}")
        return

    first, second = st.columns(2)
    first.metric("Balance", f"R$ {float(balance['balance']):,.2f}")
    second.metric("Card limit", f"R$ {float(profile['card_limit']):,.2f}")
    third, fourth = st.columns(2)
    third.metric("Card", profile["card_status"])
    fourth.metric("Segment", profile["segment"])


def render_trace_panel(api_url: str, session_id: str) -> None:
    st.subheader("Harness Trace")
    try:
        trace_payload = fetch_trace(api_url, session_id)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Trace lookup failed: {exc}")
        return

    trace = trace_payload.get("trace")
    if trace is None:
        st.info("No trace recorded for this session yet.")
        return

    route = trace.get("route", "unknown")
    requires_confirmation = "Yes" if trace.get("requires_confirmation") else "No"
    source_count = len(trace.get("grounding_sources") or [])

    first, second, third = st.columns(3)
    first.metric("Route", route)
    second.metric("HITL", requires_confirmation)
    third.metric("Sources", source_count)

    pending = trace.get("pending_operation")
    if pending:
        st.warning(f"Checkpoint pending: {pending}")
    elif route == "emergency":
        st.error("Emergency path executed.")
    elif route == "faq_fast_path" and source_count == 0:
        st.warning("Safe fail without official context.")
    else:
        st.success("Flow completed or awaiting next turn.")

    with st.expander("Trace payload", expanded=False):
        st.code(json.dumps(trace, indent=2, ensure_ascii=False), language="json")


def render_evidence_panel(api_url: str, session_id: str) -> None:
    st.subheader("RAG Evidence")
    trace = fetch_trace(api_url, session_id).get("trace")
    if not trace or trace.get("route") != "faq_fast_path":
        st.info("Evidence appears after a documental question.")
        return

    sources = trace.get("grounding_sources") or []
    st.metric("Official sources", len(sources))
    if not sources:
        st.warning("No official source was returned.")
        return

    for source in sources:
        st.markdown(f"<div class='source-pill'>{source}</div>", unsafe_allow_html=True)


def render_audit_panel(api_url: str, customer_id: str) -> None:
    st.subheader("Critical Audit")
    try:
        events = fetch_audit_events(api_url, customer_id)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Audit lookup failed: {exc}")
        return

    if not events:
        st.info("No critical events recorded yet.")
        return

    st.metric("Events", len(events))
    for event in reversed(events[-8:]):
        with st.expander(f"{event['event_type']} | {event['timestamp']}", expanded=False):
            st.json(event)


def render_observability_panel(api_url: str) -> None:
    st.subheader("Observability")
    try:
        status = fetch_observability_status(api_url)["langsmith"]
    except Exception as exc:  # noqa: BLE001
        st.error(f"Observability lookup failed: {exc}")
        return

    first, second = st.columns(2)
    first.metric("LangSmith SDK", "Available" if status["available"] else "Missing")
    second.metric("Tracing", "Enabled" if status["enabled"] else "Disabled")

    st.caption(f"Project: {status.get('project') or '-'}")
    st.caption(f"Endpoint: {status.get('endpoint') or '-'}")

    if not status["enabled"]:
        st.info("Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY to send traces to LangSmith.")


def render_knowledge_panel(api_url: str) -> None:
    st.subheader("Knowledge Base")
    try:
        status = fetch_knowledge_status(api_url)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Knowledge lookup failed: {exc}")
        return

    first, second = st.columns(2)
    first.metric("Documents", status["document_count"])
    second.metric("PDF", "Ingested" if status["pdf_ingested"] else "Fallback")
    st.metric("Official web sources", "Loaded" if status["web_sources_loaded"] else "Missing")

    with st.expander("Sources", expanded=False):
        for source in status["sources"]:
            st.markdown(f"<div class='source-pill'>{source}</div>", unsafe_allow_html=True)


def main() -> None:
    configure_page("Agent Ops Dashboard")
    render_header(
        "Agent Ops Dashboard",
        "Painel tecnico para acompanhar estado, rota, HITL, RAG, payloads e auditoria em outra tela.",
    )
    api_url, session_id, customer_id = render_sidebar()

    if st.button("Refresh dashboard", type="primary"):
        st.rerun()

    left, center, right = st.columns([1.05, 1.25, 1.05])
    with left:
        render_customer_panel(api_url, customer_id)
        render_audit_panel(api_url, customer_id)
    with center:
        render_trace_panel(api_url, session_id)
    with right:
        render_observability_panel(api_url)
        render_knowledge_panel(api_url)
        render_evidence_panel(api_url, session_id)


if __name__ == "__main__":
    main()
