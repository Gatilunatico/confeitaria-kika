"""Vitrine pública: catálogo de produtos e solicitação de orçamento (sem login)."""

import logging

import streamlit as st

from components.brand_theme import LOGO_PATH, PAGE_ICON

from components.product_card import inject_storefront_css, render_product_card
from components.quote_dialog import (
    PRICE_NOTICE,
    PRIVACY_PAGE,
    open_dialog,
    quote_dialog,
    render_last_confirmation,
)
from config import load_settings
from services.diagnostics import config_diagnosis  # só para o log do servidor
from services.product_service import Product, list_categories
from services.quote_service import normalize_origin
from services.repository import DatabaseConfigError, Repository, get_repository

log = logging.getLogger("doceflow.vitrine")
settings = load_settings()
st.set_page_config(page_title=settings.store_name, page_icon=PAGE_ICON, layout="centered")
inject_storefront_css()

LOGO = LOGO_PATH  # círculo pink da marca, fundo transparente
ORDER_PAGE = "pages/public/order.py"

# Origem da visita (?origem=instagram ou ?utm_source=instagram), guardada na 1ª carga.
if "origin" not in st.session_state:
    st.session_state["origin"] = normalize_origin(
        st.query_params.get("origem") or st.query_params.get("utm_source")
    )


@st.cache_resource(show_spinner=False)
def _repository(backend: str, sqlite_path: str, store_slug: str, url: str, key_hint: str) -> Repository:
    return get_repository(settings)


def load_catalog() -> tuple[Repository | None, list[Product], str | None]:
    try:
        repo = _repository(settings.db_backend, str(settings.sqlite_path), settings.store_slug,
                           settings.supabase_url or "", (settings.supabase_key or "")[:12])
        # Só produtos publicados. No Supabase o RLS já garante isso para o visitante;
        # o filtro aqui cobre o SQLite local, que não tem RLS.
        return repo, [p for p in repo.list_products() if p.published], None
    except DatabaseConfigError as exc:
        diagnosis = config_diagnosis(settings, exc)
    except Exception as exc:
        diagnosis = config_diagnosis(settings, exc.__cause__ or exc)
    log.error("Falha ao carregar catálogo: %s", diagnosis)  # só no log, nunca na tela
    _repository.clear()  # não guarda em cache um repositório quebrado
    return None, [], diagnosis


repo, products, catalog_diagnosis = load_catalog()

# ---------- Cabeçalho ----------
with st.container(key="df_hero"):  # cartão rosa-claro da marca (estilo em components/product_card.py)
    col_logo, col_text = st.columns([1, 2.2], vertical_alignment="center")
    with col_logo:
        if LOGO.exists():
            st.image(str(LOGO), width=180)
    with col_text:
        st.title(settings.store_name)
        st.markdown('<p class="df-tagline">Confeitaria artesanal: bolos, cupcakes e doces feitos com carinho '
                    'para a sua festa.</p>', unsafe_allow_html=True)
        st.markdown('<a class="df-cta" href="#catalogo" target="_self">Ver catálogo e pedir orçamento</a>',
                    unsafe_allow_html=True)

render_last_confirmation()

# ---------- Catálogo ----------
st.header("Catálogo", anchor="catalogo")

if repo is None:
    # O diagnóstico (variáveis ausentes, tipo do erro) vai SÓ para o log do servidor: a cliente
    # não deve ver detalhes de infraestrutura (Etapa 6). A equipe consulta em "Manage app → Logs".
    st.error("O catálogo está indisponível no momento. Tente novamente em alguns minutos.")
elif not products:
    st.warning("Nenhum produto cadastrado no momento.")
else:
    st.info(PRICE_NOTICE, icon="ℹ️")
    with st.container(border=True):
        st.markdown("**Já sabe o que quer?** Monte um pedido com um ou vários produtos. "
                    "Para tirar dúvidas antes, use **Solicitar orçamento** em cada produto.")
        try:
            st.page_link(ORDER_PAGE, label="Fazer um pedido", icon="🛒")
        except Exception:  # página executada fora do app principal
            st.markdown("[🛒 Fazer um pedido](/pedido)")
    featured =[p for p in products if p.featured]
    if featured:
        st.subheader("⭐ Destaques")
        for row_start in range(0, len(featured), 2):
            cols = st.columns(2)
            for col, product in zip(cols, featured[row_start : row_start + 2]):
                with col:
                    render_product_card(product, open_dialog, key_prefix="feat")
        st.subheader("Todos os produtos")
    category =st.pills("Categoria", ["Todos", *list_categories(products)], default="Todos", key="category")
    category = category or "Todos"
    visible = [p for p in products if category == "Todos" or p.category == category]
    if not visible:
        st.warning("Nenhum produto nesta categoria no momento.")
    for row_start in range(0, len(visible), 2):
        cols = st.columns(2)
        for col, product in zip(cols, visible[row_start : row_start + 2]):
            with col:
                render_product_card(product, open_dialog)

if st.session_state.get("dialog_product"):
    quote_dialog(st.session_state["dialog_product"], products, repo, settings.store_name)

st.divider()
try:
    st.page_link(PRIVACY_PAGE, label="Aviso de privacidade")
except Exception:  # página executada fora do app principal
    st.markdown("[Aviso de privacidade](/privacidade)")
st.caption(f"{settings.store_name} · Vitrine digital por {settings.app_name}")
