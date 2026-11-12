"""Marketing: gera legenda e imagem de post para o Instagram a partir do catálogo.

Exige o mesmo login do painel administrativo.
"""

import logging

import streamlit as st

from config import load_settings
from database import get_repository
from services.caption_generator import TEMPLATE_TYPES, generate_caption, load_template
from services.post_generator import generate_post

log = logging.getLogger("doceflow.marketing")
settings = load_settings()
st.set_page_config(page_title=f"{settings.app_name} · Marketing", page_icon="📣", layout="wide")
st.title("Marketing · Instagram")

if not st.session_state.get("admin_ok"):
    st.warning("Entre primeiro no painel administrativo para usar o marketing.")
    st.markdown("[Ir para o login do painel](/admin)")
    st.stop()

try:
    repo = st.session_state.get("admin_repo") or get_repository(settings)
    products = [p for p in repo.list_products() if p.available]
except Exception as exc:
    log.error("Falha ao carregar produtos: %s", type(exc).__name__)
    st.error("Não foi possível carregar os produtos agora.")
    st.stop()

if not products:
    st.info("Cadastre produtos disponíveis no painel para gerar posts.")
    st.stop()

by_slug = {p.slug: p for p in products}
c1, c2 = st.columns(2)
kind = c1.selectbox("Tipo de post", TEMPLATE_TYPES, format_func=lambda k: load_template(k)["nome"], key="mk_kind")
slug = c2.selectbox("Produto", list(by_slug), format_func=lambda s: by_slug[s].name, key="mk_product")
extra = st.text_area("Texto extra (opcional)", max_chars=300, placeholder="Ex.: válido até sexta-feira")
link = st.text_input("Link da vitrine (opcional)", placeholder="https://seu-app.streamlit.app/?origem=instagram")

product = by_slug[slug]
left, right = st.columns(2)
with left:
    st.subheader("Legenda")
    caption = generate_caption(kind, product, extra, link.strip() or None)
    st.code(caption, language=None)
    st.caption("Use o ícone de copiar no canto do quadro. Preços sempre como 'a partir de'.")
with right:
    st.subheader("Imagem do post (1080 × 1080)")
    png = generate_post(kind, product)
    st.image(png, width="stretch")
    st.download_button("Baixar imagem", png, file_name=f"post-{kind}-{slug}.png", mime="image/png")
