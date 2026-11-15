"""DoceFlow · ponto de entrada histórico, hoje IGUAL à vitrine (public_app.py).

O app publicado mais antigo no Streamlit Community Cloud usa `doceflow/app.py` como arquivo
principal, e o Cloud não permite trocar esse arquivo de um app já publicado. Para não apagar
o app (nem mudar o endereço que as clientes já conhecem), este arquivo passou a abrir SÓ a
vitrine. O painel administrativo é um app separado: admin_app.py (kika-cakes-painel).

Não acrescente páginas aqui: mantenha este arquivo idêntico em comportamento ao public_app.py
(o teste test_app_py_is_the_public_storefront garante isso).
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
st.navigation(PUBLIC_PAGES, position="hidden").run()
