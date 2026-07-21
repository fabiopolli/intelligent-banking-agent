from __future__ import annotations

import time

import streamlit as st

from frontend.ui_common import (
    DEFAULT_API_URL,
    DEFAULT_CUSTOMER_ID,
    DEFAULT_SESSION_ID,
    DEMO_ADMIN_TOKEN,
    DEMO_CUSTOMER_TOKEN,
    DEMO_MANAGER_TOKEN,
    PROMPTS,
    authenticate_demo_identity,
    configure_page,
    render_header,
    send_chat_message,
)


def init_state() -> None:
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("selected_prompt", PROMPTS["Tarifas"])
    st.session_state.setdefault("last_result", None)
    st.session_state.setdefault("last_latency_ms", None)
    st.session_state.setdefault("last_render_latency_ms", None)
    st.session_state.setdefault("render_started_at", None)
    st.session_state.setdefault("demo_identity", None)
    st.session_state.setdefault("demo_profile", "customer")


DEMO_PROFILES = {
    "customer": ("Cliente — Fabio (123)", DEMO_CUSTOMER_TOKEN),
    "manager": ("Gerente — leitura de clientes", DEMO_MANAGER_TOKEN),
    "admin": ("Administrador — leitura e operações", DEMO_ADMIN_TOKEN),
}


def format_brl(value: float) -> str:
    rendered = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {rendered}"


def render_sidebar() -> tuple[str, str, str, str] | None:
    st.sidebar.header("Atendimento")
    api_url = st.sidebar.text_input("API URL", value=DEFAULT_API_URL)
    identity = st.session_state.get("demo_identity")
    if identity is None:
        profile_key = st.sidebar.selectbox(
            "Perfil de demonstração",
            options=list(DEMO_PROFILES),
            format_func=lambda key: DEMO_PROFILES[key][0],
        )
        if st.sidebar.button("Entrar na demo", type="primary", use_container_width=True):
            try:
                identity = authenticate_demo_identity(api_url, DEMO_PROFILES[profile_key][1])
                st.session_state["demo_identity"] = identity
                st.session_state["demo_profile"] = profile_key
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.sidebar.error(f"Falha na autenticação da demo: {exc}")
        return None

    profile_key = st.session_state["demo_profile"]
    st.sidebar.success(f"Identidade: {identity['principal_id']} ({identity['role']})")
    if st.sidebar.button("Sair da demo", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    session_id = st.sidebar.text_input("Session ID", value=DEFAULT_SESSION_ID)
    if identity["role"] == "customer":
        customer_id = st.sidebar.text_input(
            "Cliente autenticado",
            value=identity["customer_id"],
            disabled=True,
        )
    else:
        customer_id = st.sidebar.text_input("Cliente alvo", value=DEFAULT_CUSTOMER_ID)
    return api_url, session_id, customer_id, DEMO_PROFILES[profile_key][1]


def render_prompt_buttons() -> None:
    st.caption("Escolha um caso de uso")
    columns = st.columns(len(PROMPTS))
    for column, (label, prompt) in zip(columns, PROMPTS.items()):
        if column.button(label, use_container_width=True):
            st.session_state["selected_prompt"] = prompt


def render_chat(api_url: str, session_id: str, customer_id: str, auth_token: str) -> None:
    render_prompt_buttons()

    for item in st.session_state["chat_history"]:
        with st.chat_message(item["role"]):
            # Streamlit treats an unescaped dollar sign as a Markdown math delimiter.
            st.write(str(item["content"]).replace("$", r"\$"))

    with st.form("customer_chat_form", clear_on_submit=False):
        message = st.text_area("Mensagem", value=st.session_state["selected_prompt"], height=120)
        submitted = st.form_submit_button("Enviar", type="primary", use_container_width=True)

    if not submitted:
        return

    st.session_state["chat_history"].append({"role": "user", "content": message})
    try:
        start = time.perf_counter()
        result = send_chat_message(api_url, session_id, customer_id, auth_token, message)
        st.session_state["last_latency_ms"] = round((time.perf_counter() - start) * 1000)
        st.session_state["last_result"] = result
        st.session_state["chat_history"].append({"role": "assistant", "content": result.get("message", "")})
        st.session_state["render_started_at"] = time.perf_counter()
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Nao foi possivel processar a mensagem: {exc}")


def render_customer_action() -> None:
    render_started_at = st.session_state.get("render_started_at")
    if render_started_at is not None:
        st.session_state["last_render_latency_ms"] = round((time.perf_counter() - render_started_at) * 1000)
        st.session_state["render_started_at"] = None
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
                f"<br>Valor: <strong>{format_brl(float(amount))}</strong>"
                if amount is not None
                else ""
            )
            if destination_key:
                detail_lines += f"<br>Chave: <code>{destination_key}</code>"
        if limit_details:
            current_limit = limit_details.get("current_limit")
            requested_limit = limit_details.get("requested_limit")
            if current_limit is not None:
                detail_lines += f"<br>Limite atual: <strong>{format_brl(float(current_limit))}</strong>"
            if requested_limit is not None:
                detail_lines += f"<br>Novo limite: <strong>{format_brl(float(requested_limit))}</strong>"
        st.markdown(
            f"""
            <div class="confirm-band">
                <strong>Confirmacao necessaria</strong><br>
                Esta operacao sensivel foi pausada.{detail_lines}<br>
                Envie <code>confirmo</code> para concluir a autenticacao adicional.
            </div>
            """,
            unsafe_allow_html=True,
        )

    latency = st.session_state.get("last_latency_ms")
    if latency is not None:
        timings = (result.get("observability") or {}).get("timings") or {}
        api_ms = int(timings.get("api_total_ms") or 0)
        network_ms = max(0, latency - api_ms)
        render_ms = st.session_state.get("last_render_latency_ms") or 0
        st.caption(f"Tempo total cliente → API → cliente: {latency} ms")
        with st.expander("Detalhes de latência", expanded=False):
            st.json(
                {
                    "frontend_round_trip_ms": latency,
                    "network_and_client_ms": network_ms,
                    "streamlit_render_ms": render_ms,
                    **timings,
                }
            )


def main() -> None:
    configure_page("Itau Chat", wide=False)
    init_state()
    render_header(
        "Itau Chat",
        "Atendimento bancario simulado com PIX, saldo, limite, emergencia e respostas documentais.",
    )
    sidebar_state = render_sidebar()
    if sidebar_state is None:
        st.info("Escolha um perfil controlado na lateral para iniciar a demonstração.")
        return
    api_url, session_id, customer_id, auth_token = sidebar_state
    render_chat(api_url, session_id, customer_id, auth_token)
    render_customer_action()


if __name__ == "__main__":
    main()
