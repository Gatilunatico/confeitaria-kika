"""DoceFlow · aplicação PÚBLICA (clientes, sem login).

Páginas: catálogo (/), pedido (/pedido) e aviso de privacidade (/privacidade).
Esta aplicação NÃO registra nem importa páginas ou serviços administrativos (login,
painel, marketing): eles ficam em admin_app.py, publicado como um app separado.
Ela grava dados só pelas funções controladas do banco (criar_lead / criar_pedido),
com a chave publishable e o RLS do Supabase.

Publicação (Streamlit Community Cloud): Main file path = doceflow/public_app.py
"""

import logging

import streamlit as st

from components.app_chrome import hide_platform_chrome

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

PUBLIC_PAGES = [
    st.Page("pages/public/catalog.py", title="Catálogo", icon="🧁", default=True),
    st.Page("pages/public/order.py", title="Fazer pedido", icon="🛒", url_path="pedido"),
    st.Page("pages/public/privacy.py", title="Aviso de privacidade", icon="🔒", url_path="privacidade"),
]

hide_platform_chrome()
st.navigation(PUBLIC_PAGES, position="hidden").run()  # sem menu lateral: a navegação é pelos links da loja
