"""Painel administrativo (acompanhamento de orçamentos e oportunidades).

Proteção provisória por senha (ADMIN_PASSWORD). Deve ser substituída
por autenticação real (ex.: Supabase Auth) antes do uso com clientes.
"""

import hmac

import streamlit as st

from config import load_settings
from database import check_connection

settings = load_settings()

st.set_page_config(page_title=f"{settings.app_name} · Admin", page_icon="🔒")
st.title("Painel administrativo")

if not settings.admin_password:
    st.error("Acesso bloqueado: defina ADMIN_PASSWORD no .env para habilitar o painel.")
    st.stop()

if not st.session_state.get("admin_ok"):
    password = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        if hmac.compare_digest(password.encode(), settings.admin_password.encode()):
            st.session_state["admin_ok"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    st.stop()

st.success("Acesso liberado.")

status = check_connection(settings)
(st.info if status.ok else st.error)(f"Banco: {status.backend}. {status.detail}")

st.write("Em construção: lista de orçamentos e funil de oportunidades.")

if st.button("Sair"):
    st.session_state.pop("admin_ok", None)
    st.rerun()
