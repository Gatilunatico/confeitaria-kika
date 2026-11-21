"""DoceFlow · aplicação ADMINISTRATIVA (proprietária, com login).

Páginas: login (/), painel, pedidos, orçamentos, produtos e Estúdio de Marketing.
Toda página administrativa chama require_admin(): sem sessão válida no SERVIDOR
(usuário do Supabase Auth ainda válido + perfil ativo em admin_profiles), volta ao login.
O menu lateral só aparece depois do login, mas ele NÃO é a proteção: o RLS do banco e
require_admin() são.

Publicação (Streamlit Community Cloud): app separado, Main file path = doceflow/admin_app.py
"""

import logging

import streamlit as st

from components.app_chrome import hide_platform_chrome
from components.brand_theme import CUPCAKE_PATH, LOGO_PATH
from config import load_settings
from services.auth_service import is_admin_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = load_settings()
logged_in = is_admin_session(st.session_state, settings)

ADMIN_PAGES = [
    st.Page("pages/admin/login.py", title="Entrar", icon="🔑", url_path="entrar", default=True,
            visibility="hidden" if logged_in else "visible"),
    st.Page("pages/admin/dashboard.py", title="Painel", icon="📊", url_path="painel"),
    st.Page("pages/admin/orders.py", title="Pedidos", icon="📦", url_path="pedidos"),
    st.Page("pages/admin/quotes.py", title="Orçamentos", icon="📋", url_path="orcamentos"),
    st.Page("pages/admin/products.py", title="Produtos", icon="🧁", url_path="produtos"),
    st.Page("pages/admin/marketing.py", title="Estúdio de Marketing", icon="📣", url_path="marketing"),
]

hide_platform_chrome()
# Logo da marca no topo do menu lateral; com o menu fechado, aparece só o cupcake.
st.logo(str(LOGO_PATH), size="large", icon_image=str(CUPCAKE_PATH))
st.navigation(ADMIN_PAGES, position="sidebar" if logged_in else "hidden").run()
