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
