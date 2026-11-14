"""Card de produto da vitrine pública e estilos visuais da loja (identidade Kika Cakes)."""

import streamlit as st

from services.product_service import Product

STOREFRONT_CSS = """
<style>
  .block-container {padding-top: 1.5rem; padding-bottom: 3rem;}
  [data-testid="stImage"] img {border-radius: 12px;}
  a.df-cta {display: inline-block; background: #E0628A; color: #FFFFFF !important;
            padding: .65rem 1.4rem; border-radius: 999px; text-decoration: none;
            font-weight: 600; margin-top: .25rem;}
  a.df-cta:hover {background: #5C3317;}
  .df-price {font-weight: 700; color: #5C3317; margin: 0;}
  @media (max-width: 640px) {
    .block-container {padding-left: 1rem; padding-right: 1rem;}
    h1 {font-size: 1.9rem !important;}
    a.df-cta {display: block; text-align: center;}
  }
</style>
"""


def inject_storefront_css() -> None:
    st.markdown(STOREFRONT_CSS, unsafe_allow_html=True)


def render_product_card(product: Product, on_request) -> None:
    """Card com foto, categoria, descrição, preço e botão de orçamento (ou indisponível)."""
    with st.container(border=True):
        if product.image_path:
            st.image(product.image_path, width="stretch")
        st.badge(product.category, color="primary")
        st.markdown(f"**{product.name}**")
        st.caption(product.description)
        st.markdown(f'<p class="df-price">{product.price_label}</p>', unsafe_allow_html=True)
        if product.available:
            st.button("Solicitar orçamento", key=f"req_{product.slug}", type="primary", width="stretch",
                      on_click=on_request, args=(product.slug,))
        else:
            st.button("Indisponível no momento", key=f"req_{product.slug}", disabled=True, width="stretch")
            st.caption("Este produto está temporariamente indisponível. Veja outras opções do catálogo.")
