"""Card de produto da vitrine pública e estilos visuais da loja (identidade Kika Cakes)."""

import streamlit as st

from components.brand_theme import SCRIPT_FONT_URL
from services.product_service import Product

# Cores da marca: components/brand_theme.py (o tema base fica em .streamlit/config.toml).
STOREFRONT_CSS = """
<style>
  .block-container {padding-top: 1.25rem; padding-bottom: 3rem;}
  [data-testid="stImage"] img {border-radius: 18px;}
  /* Cartão de apresentação no topo da vitrine (st.container(key="df_hero")) */
  .st-key-df_hero {background: #F2D0D0; border-radius: 28px; padding: 1.25rem 1.5rem 1.5rem;
                   border: 2px solid #D9849B;}
  .st-key-df_hero [data-testid="stImage"] img {border-radius: 50%;}
  /* Botão principal da vitrine: pink da marca; texto branco grande e em negrito (contraste AA p/ texto grande) */
  a.df-cta {display: inline-block; background: #F24484; color: #FFFFFF !important; font-weight: 800;
            font-size: 1.2rem; padding: .7rem 1.6rem; border-radius: 999px; text-decoration: none;
            margin-top: .35rem; box-shadow: 0 4px 0 #D94E73;}
  a.df-cta:hover {background: #D94E73; box-shadow: 0 4px 0 #B8345A;}
  .df-price {font-weight: 800; color: #B8345A; margin: 0; font-size: 1.05rem;}
  .df-tagline {color: #6B1B36; font-size: 1.05rem; margin: .1rem 0 .4rem;}
  /* Cartões de produto: borda rosa antigo e cantos arredondados (o tema dá a cor da borda) */
  [data-testid="stVerticalBlockBorderWrapper"] {border-radius: 20px;}
  @media (max-width: 640px) {
    .block-container {padding-left: 1rem; padding-right: 1rem;}
    h1 {font-size: 2.1rem !important;}
    a.df-cta {display: block; text-align: center;}
    .st-key-df_hero {padding: 1rem;}
    .st-key-df_hero [data-testid="stFullScreenFrame"] {display: flex; justify-content: center;}
    .st-key-df_hero h1, .df-tagline {text-align: center;}
  }
</style>
"""

# Títulos em letra cursiva (próxima do logo) só nas páginas públicas: no painel, a Nunito do tema.
HEADINGS_CSS = f"""
<style>
  @import url('{SCRIPT_FONT_URL}');
  h1, h2 {{font-family: 'Lobster', 'Nunito', cursive !important; font-weight: 400 !important;
           color: #B8345A !important; letter-spacing: .3px;}}
</style>
"""


def inject_storefront_css(script_headings: bool = True) -> None:
    st.markdown(STOREFRONT_CSS, unsafe_allow_html=True)
    if script_headings:
        st.markdown(HEADINGS_CSS, unsafe_allow_html=True)


def _md_safe(text: str) -> str:
    """Categoria vem do cadastro: remove caracteres que quebrariam a marcação do badge."""
    return "".join(ch for ch in text if ch not in "[]:*_`\\<>")


def render_product_card(product: Product, on_request, key_prefix: str = "req", preview: bool = False) -> None:
    """Card com foto, categoria, descrição, preço e botão de orçamento (ou indisponível).

    preview=True: mesma aparência da vitrine, para a dona conferir no painel (botão inativo).
    """
    with st.container(border=True):
        image = product.display_image
        if image:
            st.image(image, width="stretch")
        if product.featured:
            st.markdown(f":primary-badge[{_md_safe(product.category)}] :orange-badge[⭐ Destaque]")
        else:
            st.badge(product.category, color="primary")
        st.markdown(f"**{product.name}**")
        st.caption(product.description)
        st.markdown(f'<p class="df-price">{product.price_label}</p>', unsafe_allow_html=True)
        if product.production_label:
            st.caption(f"⏱️ {product.production_label}")
        key = f"{key_prefix}_{product.slug}"
        if product.available:
            st.button("Solicitar orçamento", key=key, type="primary", width="stretch", disabled=preview,
                      on_click=None if preview else on_request, args=None if preview else (product.slug,))
        else:
            st.button("Indisponível no momento", key=key, disabled=True, width="stretch")
            st.caption("Este produto está temporariamente indisponível. Veja outras opções do catálogo.")
