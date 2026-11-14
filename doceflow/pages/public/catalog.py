"""Vitrine pública: catálogo de produtos e solicitação de orçamento (sem login)."""

import logging

import streamlit as st

from components.product_card import inject_storefront_css, render_product_card
from components.quote_dialog import (
    PRICE_NOTICE,
    PRIVACY_PAGE,
    open_dialog,
    quote_dialog,
    render_last_confirmation,
)
from config import BASE_DIR, load_settings
from services.product_service import Product, list_categories
from services.quote_service import normalize_origin
from services.repository import DatabaseConfigError, Repository, get_repository

log = logging.getLogger("doceflow.vitrine")
settings = load_settings()
st.set_page_config(page_title=settings.store_name, page_icon="🧁", layout="centered")
inject_storefront_css()

LOGO = BASE_DIR / "assets" / "logo" / "logo-kika-cakes.png"

# Origem da visita (?origem=instagram ou ?utm_source=instagram), guardada na 1ª carga.
if "origin" not in st.session_state:
    st.session_state["origin"] = normalize_origin(
        st.query_params.get("origem") or st.query_params.get("utm_source")
    )


@st.cache_resource(show_spinner=False)
def _repository(backend: str, sqlite_path: str, store_slug: str, url: str, key_hint: str) -> Repository:
    return get_repository(settings)


def _config_diagnosis(exc: Exception | None) -> str:
    """Motivo da falha sem expor valores secretos (só nomes de variáveis e tipo do erro)."""
    secrets_state = "ok"
    try:
        _ = list(st.secrets.keys())
    except Exception as secrets_exc:  # sem secrets.toml ou TOML inválido
        secrets_state = f"não lidos ({type(secrets_exc).__name__})"
    missing = [name for name, value in (("SUPABASE_URL", settings.supabase_url),
                                        ("SUPABASE_KEY", settings.supabase_key)) if not value]
    parts = [f"DB_BACKEND={settings.db_backend}", f"Secrets: {secrets_state}"]
    if settings.db_backend == "supabase":
        if missing:
            parts.append("faltando: " + ", ".join(missing))
        if settings.supabase_url and not settings.supabase_url.rstrip("/").endswith(".supabase.co"):
            parts.append("SUPABASE_URL não parece ser a URL da API (https://<id>.supabase.co)")
        if settings.supabase_key and not settings.supabase_key.startswith(("sb_publishable_", "eyJ")):
            parts.append("SUPABASE_KEY não parece ser a chave publishable/anon")
    if exc is not None:
        message = str(exc)
        for secret in (settings.supabase_key, settings.supabase_url):
            if secret:
                message = message.replace(secret, "***")
        parts.append(f"erro: {type(exc).__name__}: {message[:160]}")
    return " · ".join(parts)


def load_catalog() -> tuple[Repository | None, list[Product], str | None]:
    try:
        repo = _repository(settings.db_backend, str(settings.sqlite_path), settings.store_slug,
                           settings.supabase_url or "", (settings.supabase_key or "")[:12])
        return repo, repo.list_products(), None
    except DatabaseConfigError as exc:
        diagnosis = _config_diagnosis(exc)
    except Exception as exc:
        diagnosis = _config_diagnosis(exc.__cause__ or exc)
    log.error("Falha ao carregar catálogo: %s", diagnosis)
    _repository.clear()  # não guarda em cache um repositório quebrado
    return None, [], diagnosis


repo, products, catalog_diagnosis = load_catalog()

# ---------- Cabeçalho ----------
col_logo, col_text = st.columns([1, 2.4], vertical_alignment="center")
with col_logo:
    if LOGO.exists():
        st.image(str(LOGO), width=170)
with col_text:
    st.title(settings.store_name)
    st.write("Bolos, cupcakes e doces artesanais feitos com carinho para a sua festa.")
    st.markdown('<a class="df-cta" href="#catalogo" target="_self">Ver catálogo e pedir orçamento</a>',
                unsafe_allow_html=True)

render_last_confirmation()

# ---------- Catálogo ----------
st.header("Catálogo", anchor="catalogo")

if repo is None:
    st.error("O catálogo está indisponível no momento. Tente novamente em alguns minutos.")
    if catalog_diagnosis:
        with st.expander("Detalhes técnicos (para a equipe)"):
            st.code(catalog_diagnosis, language=None)
elif not products:
    st.warning("Nenhum produto cadastrado no momento.")
else:
    st.info(PRICE_NOTICE, icon="ℹ️")
    category = st.pills("Categoria", ["Todos", *list_categories(products)], default="Todos", key="category")
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
