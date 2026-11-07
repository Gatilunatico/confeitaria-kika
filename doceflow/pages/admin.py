"""Painel administrativo: consulta de leads da confeitaria.

- SQLite (testes locais): senha provisória ADMIN_PASSWORD.
- Supabase: login da dona via Supabase Auth (e-mail e senha). O RLS só
  devolve os leads da confeitaria cujo owner_user_id é o usuário logado.
  Nenhuma chave administrativa (service_role) é usada.
"""

import hmac
import logging

import pandas as pd
import streamlit as st

from config import load_settings
from database import SupabaseRepository, check_connection, get_repository, get_supabase_client

log = logging.getLogger("doceflow.admin")
settings = load_settings()

st.set_page_config(page_title=f"{settings.app_name} · Admin", page_icon="🔒", layout="wide")
st.title("Painel administrativo")


def _logout() -> None:
    client = st.session_state.pop("admin_client", None)
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    st.session_state.pop("admin_ok", None)


# ---------------------------------------------------------------- login
if not st.session_state.get("admin_ok"):
    if settings.db_backend == "supabase":
        with st.form("login"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
        if submitted:
            try:
                client = get_supabase_client(settings)
                client.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state["admin_client"] = client
                st.session_state["admin_ok"] = True
                st.rerun()
            except Exception as exc:
                log.warning("Login admin recusado: %s", type(exc).__name__)
                st.error("E-mail ou senha inválidos.")
        st.stop()

    if not settings.admin_password:
        st.error("Acesso bloqueado: defina ADMIN_PASSWORD no .env para habilitar o painel.")
        st.stop()
    with st.form("login_local"):
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
    if submitted:
        if hmac.compare_digest(password.encode(), settings.admin_password.encode()):
            st.session_state["admin_ok"] = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    st.stop()


# ---------------------------------------------------------------- painel
st.success("Acesso liberado.")
status = check_connection(settings)
(st.info if status.ok else st.error)(f"Banco: {status.backend}. {status.detail}")

try:
    if settings.db_backend == "supabase":
        repo = SupabaseRepository(st.session_state["admin_client"], settings.store_slug)
    else:
        repo = get_repository(settings)
    leads = repo.list_leads()
except Exception as exc:
    log.error("Falha ao listar leads: %s", type(exc).__name__)
    st.error("Não foi possível carregar os leads agora.")
    leads = []

st.subheader(f"Leads ({len(leads)})")
if leads:
    df = pd.DataFrame(leads).rename(
        columns={
            "protocolo": "Protocolo", "created_at": "Recebido em", "status": "Status",
            "cliente_nome": "Cliente", "cliente_whatsapp": "WhatsApp", "produto_nome": "Produto",
            "quantidade": "Qtd.", "unidade": "Unidade", "data_desejada": "Data desejada",
            "modalidade": "Retirada/Entrega", "observacoes": "Observações", "origem": "Origem",
        }
    )
    st.dataframe(df, hide_index=True, width="stretch")
else:
    st.write("Nenhuma solicitação recebida ainda.")

st.caption("Dados pessoais de clientes: não exporte, não compartilhe e não tire prints desnecessários.")
st.button("Sair", on_click=_logout)
