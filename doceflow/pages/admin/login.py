"""Login da área administrativa (raiz do admin_app.py; /admin no app combinado legado)."""

import logging

import streamlit as st

from components.brand_theme import LOGO_PATH, PAGE_ICON

from config import load_settings
from services.auth_service import (
    DASHBOARD_PAGE,
    MIN_PASSWORD,
    AuthError,
    authorized_admin_repository,
    cancel_password_recovery,
    complete_password_reset,
    locked_minutes,
    login_local,
    login_supabase,
    recovery_active,
    request_password_reset,
    start_password_recovery,
)

log = logging.getLogger("doceflow.auth")
settings = load_settings()
st.set_page_config(page_title=f"{settings.app_name} · Entrar", page_icon=PAGE_ICON, layout="centered")

if authorized_admin_repository(st.session_state, settings) is not None:
    st.switch_page(DASHBOARD_PAGE)

_, logo_col, _ = st.columns([1, 1, 1])
if LOGO_PATH.exists():
    logo_col.image(str(LOGO_PATH), width="stretch")
st.title("Painel administrativo")

minutes = locked_minutes(st.session_state)
if minutes:
    st.error(f"Muitas tentativas sem sucesso. Tente novamente em {minutes} min.")
    st.stop()

RESET_SENT = ("Se este e-mail tiver acesso ao painel, enviamos um link para criar uma nova senha. "
              "Ele vale por 1 hora. Confira também a caixa de spam.")


def new_password_form() -> None:
    """Depois que o link ou o código foi validado no servidor do Supabase."""
    st.subheader("Criar nova senha")
    with st.form("new_password"):
        first = st.text_input("Nova senha", type="password", key="np_1",
                              help=f"Pelo menos {MIN_PASSWORD} caracteres. Use letras e números.")
        second = st.text_input("Repita a nova senha", type="password", key="np_2")
        save = st.form_submit_button("Salvar nova senha", type="primary")
    if save:
        try:
            complete_password_reset(st.session_state, first, second)
        except AuthError as exc:
            st.error(str(exc))
        else:
            st.session_state["reset_done"] = True
            st.rerun()
    if st.button("Cancelar", key="np_cancel"):
        cancel_password_recovery(st.session_state)
        st.rerun()


def forgot_password() -> None:
    with st.expander("Esqueceu a senha?"):
        st.write("Informe o e-mail cadastrado. Você vai receber um link (ou um código) para criar uma nova senha.")
        with st.form("forgot"):
            reset_email = st.text_input("E-mail cadastrado", key="fp_email")
            send = st.form_submit_button("Enviar link")
        if send:
            try:
                request_password_reset(st.session_state, settings, reset_email)
            except AuthError as exc:
                st.error(str(exc))
            else:
                st.success(RESET_SENT)
        st.caption("Recebeu um código de 6 dígitos no e-mail? Digite aqui:")
        with st.form("recovery_code"):
            code_email = st.text_input("E-mail cadastrado", key="rc_email")
            code = st.text_input("Código de 6 dígitos", max_chars=6, key="rc_code")
            check = st.form_submit_button("Validar código")
        if check:
            try:
                start_password_recovery(st.session_state, settings, email=code_email, code=code)
            except AuthError as exc:
                st.error(str(exc))
            else:
                st.rerun()


if settings.db_backend == "supabase":
    # Link do e-mail de recuperação: <painel>/?token_hash=...&type=recovery
    if st.query_params.get("type") == "recovery" and st.query_params.get("token_hash"):
        token = st.query_params.get("token_hash")
        st.query_params.clear()  # o token não fica no endereço nem no histórico do navegador
        try:
            start_password_recovery(st.session_state, settings, token_hash=token)
        except AuthError as exc:
            st.session_state["recovery_error"] = str(exc)
        st.rerun()
    if error := st.session_state.pop("recovery_error", None):
        st.error(error)
    if recovery_active(st.session_state):
        new_password_form()
        st.stop()
    if st.session_state.pop("reset_done", False):
        st.success("Senha alterada! Agora entre com o seu e-mail e a nova senha.")

    with st.form("login"):
        email = st.text_input("E-mail")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar", type="primary")
    if submitted:
        try:
            login_supabase(st.session_state, settings, email, password)
        except AuthError as exc:
            st.error(str(exc))
        else:
            st.switch_page(DASHBOARD_PAGE)
    forgot_password()
    st.stop()

if not settings.admin_password:
    log.error("Painel bloqueado: ADMIN_PASSWORD não configurada (modo SQLite)")
    st.error("O acesso ao painel ainda não foi configurado. Fale com o suporte do DoceFlow.")
    st.stop()
with st.form("login_local"):
    password = st.text_input("Senha", type="password")
    submitted = st.form_submit_button("Entrar", type="primary")
st.caption("Esqueceu a senha? No modo local, fale com o suporte do DoceFlow.")
if submitted:
    try:
        login_local(st.session_state, settings, password)
    except AuthError as exc:
        st.error(str(exc))
        st.stop()
    st.switch_page(DASHBOARD_PAGE)
