from __future__ import annotations

import time

import streamlit as st

from frontend.ui_common import (
    DEFAULT_API_URL,
    DEFAULT_CUSTOMER_ID,
    DEFAULT_SESSION_ID,
    PROMPTS,
    configure_page,
    render_header,
    send_chat_message,
)


def init_state() -> None:
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("selected_prompt", PROMPTS["Tarifas"])
    st.session_state.setdefault("last_result", None)
    st.session_state.setdefault("last_latency_ms", None)


def render_sidebar() -> tuple[str, str, str, str]:
    st.sidebar.header("Atendimento")
    api_url = st.sidebar.text_input("API URL", value=DEFAULT_API_URL)
    session_id = st.sidebar.text_input("Session ID", value=DEFAULT_SESSION_ID)
    customer_id = st.sidebar.text_input("Customer ID", value=DEFAULT_CUSTOMER_ID)
    role = st.sidebar.selectbox("Role", options=["customer", "manager", "admin"], index=0)
    return api_url, session_id, customer_id, role


def render_prompt_buttons() -> None:
    st.caption("Escolha um caso de uso")
    columns = st.columns(len(PROMPTS))
    for column, (label, prompt) in zip(columns, PROMPTS.items()):
        if column.button(label, use_container_width=True):
            st.session_state["selected_prompt"] = prompt


def render_chat(api_url: str, session_id: str, customer_id: str, role: str) -> None:
    render_prompt_buttons()

    for item in st.session_state["chat_history"]:
        with st.chat_message(item["role"]):
            st.write(item["content"])

    with st.form("customer_chat_form", clear_on_submit=False):
        message = st.text_area("Mensagem", value=st.session_state["selected_prompt"], height=120)
        submitted = st.form_submit_button("Enviar", type="primary", use_container_width=True)

    if not submitted:
        return

    st.session_state["chat_history"].append({"role": "user", "content": message})
    try:
        start = time.perf_counter()
        result = send_chat_message(api_url, session_id, customer_id, role, message)
        st.session_state["last_latency_ms"] = round((time.perf_counter() - start) * 1000)
        st.session_state["last_result"] = result
        st.session_state["chat_history"].append({"role": "assistant", "content": result.get("message", "")})
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Nao foi possivel processar a mensagem: {exc}")


def render_customer_action() -> None:
    result = st.session_state.get("last_result")
    if not result:
        return

    if result.get("requires_confirmation"):
        pix_details = result.get("pix_details") or {}
        limit_details = result.get("limit_details") or {}
        detail_lines = ""
        if pix_details:
            amount = pix_details.get("amount")
            destination_key = pix_details.get("destination_key")
            detail_lines = (
                f"<br>Valor: <strong>R$ {float(amount):.2f}</strong>"
                if amount is not None
                else ""
            )
            if destination_key:
                detail_lines += f"<br>Chave: <code>{destination_key}</code>"
        if limit_details:
            current_limit = limit_details.get("current_limit")
            requested_limit = limit_details.get("requested_limit")
            if current_limit is not None:
                detail_lines += f"<br>Limite atual: <strong>R$ {float(current_limit):.2f}</strong>"
            if requested_limit is not None:
                detail_lines += f"<br>Novo limite: <strong>R$ {float(requested_limit):.2f}</strong>"
        st.markdown(
            f"""
            <div class="confirm-band">
                <strong>Confirmacao necessaria</strong><br>
                Esta operacao sensivel foi pausada.{detail_lines}<br>
                Para esta demo, envie <code>confirmo</code>
                para simular uma autenticacao adicional no app.
            </div>
            """,
            unsafe_allow_html=True,
        )

    latency = st.session_state.get("last_latency_ms")
    if latency is not None:
        st.caption(f"Tempo de resposta: {latency} ms")


def main() -> None:
    configure_page("Itau Chat", wide=False)
    init_state()
    render_header(
        "Itau Chat",
        "Atendimento bancario simulado com PIX, saldo, limite, emergencia e respostas documentais.",
    )
    api_url, session_id, customer_id, role = render_sidebar()
    render_chat(api_url, session_id, customer_id, role)
    render_customer_action()


if __name__ == "__main__":
    main()
