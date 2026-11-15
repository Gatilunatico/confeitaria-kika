"""Login da área administrativa (raiz do admin_app.py; /admin no app combinado legado)."""

import logging

import streamlit as st

from config import load_settings
from services.auth_service import (
    DASHBOARD_PAGE,
    AuthError,
    authorized_admin_repository,
    locked_minutes,
    login_local,
    login_supabase,
)

log = logging.getLogger("doceflow.auth")
settings = load_settings()
st.set_page_config(page_title=f"{settings.app_name} · Entrar", page_icon="🔒", layout="centered")

if authorized_admin_repository(st.session_state, settings) is not None:
    st.switch_page(DASHBOARD_PAGE)

st.title("Painel administrativo")

minutes = locked_minutes(st.session_state)
if minutes:
    st.error(f"Muitas tentativas sem sucesso. Tente novamente em {minutes} min.")
    st.stop()

if settings.db_backend == "supabase":
    with st.form("login"):
        email = st.text_input("E-mail")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
    if submitted:
        try:
            login_supabase(st.session_state, settings, email, password)
        except AuthError as exc:
            st.error(str(exc))
            st.stop()
        st.switch_page(DASHBOARD_PAGE)
    st.stop()

if not settings.admin_password:
    log.error("Painel bloqueado: ADMIN_PASSWORD não configurada (modo SQLite)")
    st.error("O acesso ao painel ainda não foi configurado. Fale com o suporte do DoceFlow.")
    st.stop()
with st.form("login_local"):
    password = st.text_input("Senha", type="password")
    submitted = st.form_submit_button("Entrar")
if submitted:
    try:
        login_local(st.session_state, settings, password)
    except AuthError as exc:
        st.error(str(exc))
        st.stop()
    st.switch_page(DASHBOARD_PAGE)
