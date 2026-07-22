from __future__ import annotations

import json
from datetime import datetime
from html import escape

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
from frontend.customer_chat import format_brl


MAX_VISIBLE_AUDIT_EVENTS = 3
AUTO_REFRESH_SECONDS = 2


def latest_audit_events(events: list[dict]) -> list[dict]:
    return list(reversed(events[-MAX_VISIBLE_AUDIT_EVENTS:]))


def build_journey_steps(trace_payload: dict) -> list[dict[str, str]]:
    trace = trace_payload.get("trace") or {}
    if not trace:
        return [{"title": "Aguardando cliente", "detail": "Envie uma mensagem no chat", "status": "pending"}]

    observability = trace.get("observability") or {}
    route = trace.get("route", "unknown")
    guardrails = observability.get("guardrails") or {}
    hitl = trace_payload.get("hitl") or {}
    tools = observability.get("tools_called") or []
    planner = observability.get("planner") or {}
    llm = observability.get("llm") or {}
    steps = [
        {"title": "Mensagem", "detail": f"Sessão {trace.get('session_id', '-')}", "status": "success"},
        {
            "title": "Guardrails",
            "detail": "Bloqueado" if guardrails.get("blocked") else "Entrada aprovada",
            "status": "blocked" if guardrails.get("blocked") else "success",
        },
        {
            "title": "Roteamento",
            "detail": planner.get("selected_tool") or route,
            "status": "success",
        },
    ]
    if route == "faq_fast_path":
        source_count = len(trace.get("grounding_sources") or [])
        steps.append({"title": "RAG oficial", "detail": f"{source_count} fonte(s)", "status": "success" if source_count else "warning"})
        provider = llm.get("provider") or "Resposta determinística"
        if llm.get("fallback_used"):
            provider = f"{provider} → {llm.get('fallback_provider') or 'fallback grounded'}"
        steps.append(
            {
                "title": "Síntese",
                "detail": provider,
                "status": "warning" if llm.get("fallback_used") else "success",
            }
        )
    elif route in {"transaction", "core_banking", "emergency"}:
        steps.append({"title": "RBAC e políticas", "detail": "Autorização nativa", "status": "success"})
        if hitl.get("encountered") or trace.get("requires_confirmation"):
            hitl_status = hitl.get("status") or "awaiting_confirmation"
            status = "warning" if hitl_status == "awaiting_confirmation" else ("blocked" if hitl_status in {"cancelled", "failed"} else "success")
            steps.append({"title": "HITL", "detail": hitl_status, "status": status})
        if tools:
            steps.append({"title": "MCP / ferramenta", "detail": str(tools[-1]), "status": "success"})
    steps.append(
        {
            "title": "Resposta",
            "detail": "Aguardando autorização" if trace.get("requires_confirmation") else "Entregue ao cliente",
            "status": "warning" if trace.get("requires_confirmation") else "success",
        }
    )
    return steps


def render_journey_panel(trace_payload: dict) -> None:
    st.subheader("Jornada da solicitação")
    steps = build_journey_steps(trace_payload)
    cards = []
    for index, step in enumerate(steps, start=1):
        cards.append(
            f"<div class='journey-step {escape(step['status'])}'>"
            f"<div class='journey-index'>ETAPA {index}</div>"
            f"<div class='journey-title'>{escape(step['title'])}</div>"
            f"<div class='journey-detail'>{escape(step['detail'])}</div>"
            "</div>"
        )
    st.markdown(f"<div class='journey-flow'>{''.join(cards)}</div>", unsafe_allow_html=True)


def render_sidebar() -> tuple[str, str, str]:
    st.sidebar.header("Inspector")
    api_url = st.sidebar.text_input("API URL", value=DEFAULT_API_URL)
    session_id = st.sidebar.text_input("Session ID", value=DEFAULT_SESSION_ID)
    customer_id = st.sidebar.text_input("Customer ID", value=DEFAULT_CUSTOMER_ID)
    return api_url, session_id, customer_id


def render_customer_panel(api_url: str, customer_id: str) -> None:
    st.subheader("Estado do cliente")
    try:
        profile = fetch_profile(api_url, customer_id)
        balance = fetch_balance(api_url, customer_id)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Falha ao consultar cliente: {exc}")
        return

    first, second = st.columns(2)
    first.metric("Saldo", format_brl(float(balance["balance"])))
    second.metric("Limite do cartão", format_brl(float(profile["card_limit"])))
    third, fourth = st.columns(2)
    third.metric("Cartão", profile["card_status"])
    fourth.metric("Segmento", profile["segment"])


def render_trace_panel(api_url: str, session_id: str) -> None:
    st.subheader("Trace do Agent Harness")
    try:
        trace_payload = fetch_trace(api_url, session_id)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Trace lookup failed: {exc}")
        return

    trace = trace_payload.get("trace")
    if trace is None:
        st.info("Ainda não há trace para esta sessão.")
        return

    route = trace.get("route", "unknown")
    hitl = trace_payload.get("hitl") or {}
    hitl_status = {
        "awaiting_confirmation": "Awaiting",
        "completed": "Completed",
        "failed": "Failed",
        "cancelled": "Cancelado",
    }.get(hitl.get("status"), "Not used")
    source_count = len(trace.get("grounding_sources") or [])
    observability = trace.get("observability") or {}
    tools_called = observability.get("tools_called") or []
    llm = observability.get("llm") or {}
    planner = observability.get("planner") or {}

    first, second = st.columns(2)
    first.metric("Rota", route)
    second.metric("HITL", hitl_status)
    third, fourth = st.columns(2)
    third.metric("Fontes", source_count)
    fourth.metric("Ferramentas", len(tools_called))
    fifth, sixth = st.columns(2)
    planner_provider = planner.get("provider") or "Not used this turn"
    fifth.metric("LLM Planner", planner_provider)
    sixth.metric("Fallback", "Sim" if planner.get("fallback_used") else "Não")
    if not planner:
        st.caption("Native Harness continuation: this turn did not require LLM intent planning.")

    pending = trace.get("pending_operation")
    if hitl.get("status") == "completed":
        st.success("HITL completed after customer confirmation.")
    elif hitl.get("status") == "cancelled":
        st.warning("Operação cancelada pelo cliente no checkpoint HITL.")
    elif pending:
        st.warning(f"Checkpoint pending: {pending}")
    elif route == "emergency":
        st.error("Emergency path executed.")
    elif route == "faq_fast_path" and source_count == 0:
        st.warning("Safe fail without official context.")
    else:
        st.success("Flow completed or awaiting next turn.")

    with st.expander("Trace payload", expanded=False):
        st.code(json.dumps(trace, indent=2, ensure_ascii=False), language="json")

    if hitl.get("encountered"):
        with st.expander("HITL lifecycle", expanded=True):
            st.caption(f"Correlation ID: {hitl.get('correlation_id')}")
            duration = hitl.get("duration_ms")
            st.caption(f"Duração: {duration} ms" if duration is not None else "Duração: não aplicável")
            st.code(json.dumps(hitl.get("events") or [], indent=2, ensure_ascii=False), language="json")

    with st.expander("Observability: tools, prompt, context and tokens", expanded=False):
        st.markdown("**Latency breakdown**")
        st.code(
            json.dumps(observability.get("timings") or {}, indent=2, ensure_ascii=False),
            language="json",
        )
        st.markdown("**Agent planner**")
        st.code(
            json.dumps(
                {
                    "provider": planner.get("provider"),
                    "model": planner.get("model"),
                    "selected_tool": planner.get("selected_tool"),
                    "fallback_selected_tool": planner.get("fallback_selected_tool"),
                    "route": planner.get("route"),
                    "fallback_used": planner.get("fallback_used"),
                    "fallback_reason": planner.get("fallback_reason"),
                    "prompt_profile": planner.get("prompt_profile"),
                    "prompt_version": planner.get("prompt_version"),
                    "prompt_hash": planner.get("prompt_hash"),
                    "token_usage": planner.get("token_usage"),
                    "duration_ms": planner.get("duration_ms"),
                },
                indent=2,
                ensure_ascii=False,
            ),
            language="json",
        )
        st.markdown("**Tools called**")
        st.code(json.dumps(tools_called, indent=2, ensure_ascii=False), language="json")
        st.markdown("**LLM provider**")
        st.code(
            json.dumps(
                {
                    "provider": llm.get("provider"),
                    "model": llm.get("model"),
                    "fallback_used": llm.get("fallback_used"),
                    "fallback_reason": llm.get("fallback_reason"),
                    "token_usage": llm.get("token_usage"),
                    "duration_ms": llm.get("duration_ms"),
                },
                indent=2,
                ensure_ascii=False,
            ),
            language="json",
        )
        if llm.get("prompt"):
            st.markdown("**Prompt sent to LLM**")
            st.code(llm["prompt"], language="text")
        approved_context = llm.get("approved_context") or observability.get("retrieval", {}).get("approved_context")
        if approved_context:
            st.markdown("**Approved context**")
            st.code(json.dumps(approved_context, indent=2, ensure_ascii=False), language="json")


def render_evidence_panel(api_url: str, session_id: str) -> None:
    st.subheader("Evidências do RAG")
    trace = fetch_trace(api_url, session_id).get("trace")
    if not trace or trace.get("route") != "faq_fast_path":
        st.info("As evidências aparecem após uma pergunta documental.")
        return

    sources = trace.get("grounding_sources") or []
    st.metric("Fontes oficiais", len(sources))
    if not sources:
        st.warning("Nenhuma fonte oficial foi retornada.")
        return

    for source in sources:
        st.markdown(f"<div class='source-pill'>{source}</div>", unsafe_allow_html=True)


def render_audit_panel(api_url: str, customer_id: str) -> None:
    st.subheader("Auditoria crítica")
    try:
        events = fetch_audit_events(api_url, customer_id)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Audit lookup failed: {exc}")
        return

    if not events:
        st.info("No critical events recorded yet.")
        return

    st.metric("Eventos", len(events))
    st.caption(f"Exibindo os {min(len(events), MAX_VISIBLE_AUDIT_EVENTS)} eventos mais recentes.")
    for event in latest_audit_events(events):
        with st.expander(f"{event['event_type']} | {event['timestamp']}", expanded=False):
            st.json(event)


def render_observability_panel(api_url: str) -> None:
    st.subheader("Observabilidade")
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
    st.subheader("Base de conhecimento")
    try:
        status = fetch_knowledge_status(api_url)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Knowledge lookup failed: {exc}")
        return

    first, second = st.columns(2)
    first.metric("Registros recuperáveis", status["document_count"])
    second.metric("Fontes oficiais", len(status.get("sources") or []))
    third, fourth = st.columns(2)
    third.metric("PDF de tarifas", "Ingerido" if status["pdf_ingested"] else "Indisponível")
    fourth.metric("Síntese documental padrão", status.get("grounded_faq_synthesizer", "desativada"))
    st.caption(
        "Os registros recuperáveis são unidades indexadas da KB, não arquivos distintos. "
        f"Reranker: {status.get('reranker', '-')}"
    )
    st.caption(
        "Snapshots oficiais: carregados"
        if status["web_sources_loaded"]
        else "Snapshots oficiais: incompletos"
    )

    with st.expander("Fontes oficiais", expanded=False):
        for source in status["sources"]:
            st.markdown(f"<div class='source-pill'>{source}</div>", unsafe_allow_html=True)


@st.fragment(run_every=f"{AUTO_REFRESH_SECONDS}s")
def render_live_dashboard(api_url: str, session_id: str, customer_id: str) -> None:
    try:
        trace_payload = fetch_trace(api_url, session_id)
    except Exception:  # noqa: BLE001
        trace_payload = {}
    render_journey_panel(trace_payload)
    st.caption(f"Atualização automática a cada {AUTO_REFRESH_SECONDS}s · {datetime.now().strftime('%H:%M:%S')}")
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


def main() -> None:
    configure_page("Agent Ops Dashboard")
    render_header(
        "Agent Ops Dashboard",
        "Painel tecnico para acompanhar estado, rota, HITL, RAG, payloads e auditoria em outra tela.",
    )
    api_url, session_id, customer_id = render_sidebar()

    render_live_dashboard(api_url, session_id, customer_id)


if __name__ == "__main__":
    main()
