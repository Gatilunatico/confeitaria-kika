"""DoceFlow: ponto de entrada e navegação.

- Área pública (sem login): catálogo com solicitação de orçamento e aviso de privacidade.
- Área administrativa (login obrigatório): painel, orçamentos, produtos e marketing.

Todas as páginas ficam registradas para que links e redirecionamentos funcionem,
mas cada página administrativa verifica a sessão no servidor (require_admin) e
leva ao login quando ela não é válida. O menu lateral só aparece após o login.
URLs mantidas: / (catálogo), /privacidade, /admin (login) e /marketing.
"""

import logging

import streamlit as st

from config import load_settings
from services.auth_service import is_admin_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = load_settings()
logged_in = is_admin_session(st.session_state, settings)

public_pages = [
    st.Page("pages/public/catalog.py", title="Catálogo", icon="🧁", default=True),
    st.Page("pages/public/privacy.py", title="Aviso de privacidade", icon="🔒", url_path="privacidade"),
]
admin_pages = [
    st.Page("pages/admin/login.py", title="Entrar", icon="🔑", url_path="admin",
            visibility="hidden" if logged_in else "visible"),
    st.Page("pages/admin/dashboard.py", title="Painel", icon="📊", url_path="painel"),
    st.Page("pages/admin/quotes.py", title="Orçamentos", icon="📋", url_path="orcamentos"),
    st.Page("pages/admin/products.py", title="Produtos", icon="🧁", url_path="produtos"),
    st.Page("pages/admin/marketing.py", title="Estúdio de Marketing", icon="📣", url_path="marketing"),
]

navigation = st.navigation(
    {"Loja": public_pages, "Administração": admin_pages},
    position="sidebar" if logged_in else "hidden",  # visitantes não veem o menu admin
)
navigation.run()
