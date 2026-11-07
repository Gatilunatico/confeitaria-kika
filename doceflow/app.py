"""DoceFlow: página inicial (catálogo público).

Nesta etapa a página só valida a configuração e a conexão com o banco.
O catálogo e o formulário de orçamento entram nas próximas etapas.
"""

import streamlit as st

from config import BASE_DIR, load_settings
from database import check_connection
from services.whatsapp import build_wa_link

settings = load_settings()

st.set_page_config(page_title=settings.app_name, page_icon="🧁", layout="centered")

logo = BASE_DIR / "assets" / "images" / "logo-kika-cakes.png"
if logo.exists():
    st.image(str(logo), width=180)

st.title(settings.app_name)
st.caption("Catálogo digital e orçamentos para confeitarias artesanais")

status = check_connection(settings)
if status.ok:
    st.success(f"Banco: {status.backend}. {status.detail}")
else:
    st.error(f"Banco: {status.backend}. {status.detail}")

if settings.whatsapp_number:
    try:
        st.link_button(
            "Falar no WhatsApp",
            build_wa_link(settings.whatsapp_number, "Olá! Vim pelo catálogo e gostaria de um orçamento."),
        )
    except ValueError as exc:
        st.warning(str(exc))
else:
    st.info("Defina WHATSAPP_NUMBER no .env para exibir o botão de WhatsApp.")

st.divider()
st.write("Em construção: catálogo de produtos e formulário de orçamento.")
