"""Pedido pela vitrine (sem login): escolher produtos e quantidades, revisar e confirmar.

O pedido só é mostrado como registrado DEPOIS que o banco devolve o protocolo.
O navegador envia apenas produto e quantidade; nome, preço e valor estimado são
recalculados no servidor (função criar_pedido / repositório). Disponibilidade e preço
final dependem da confirmação da confeitaria.
"""

import logging
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from components.product_card import inject_storefront_css
from components.quote_dialog import PRIVACY_PAGE, PRIVACY_SHORT
from config import load_settings
from services.order_service import ADDRESS_MAX, DELIVERY, MAX_ITEMS, summarize, validate_order
from services.product_service import format_brl
from services.quote_service import (
    FULFILLMENT_OPTIONS,
    MAX_DAYS_AHEAD,
    NOTES_MAX,
    LeadPersistenceError,
    LeadValidationError,
    format_br_phone,
    normalize_origin,
)
from services.repository import get_repository
from services.whatsapp_service import order_wa_link

log = logging.getLogger("doceflow.pedido")
settings = load_settings()
st.set_page_config(page_title=f"{settings.store_name} · Fazer pedido", page_icon="🛒", layout="centered")
inject_storefront_css()

ORDER_NOTICE = ("Os valores são **estimados** (preço inicial × quantidade). A confeitaria confirma a "
                "disponibilidade e o **valor final** pelo WhatsApp antes de começar a produção.")


@st.cache_resource(show_spinner=False)
def _repository(backend: str, sqlite_path: str, store_slug: str, url: str, key_hint: str):
    return get_repository(settings)


def _nonce() -> int:
    """Chave do formulário: trocar o número limpa todos os campos depois de um pedido."""
    return st.session_state.setdefault("ord_nonce", 0)


def k(name: str) -> str:
    return f"ord_{_nonce()}_{name}"


def _privacy_link(label: str) -> None:
    try:
        st.page_link(PRIVACY_PAGE, label=label)
    except Exception:
        st.markdown(f"[{label}](/privacidade)")


def render_done(done: dict) -> None:
    order, request, summary = done["order"], done["request"], done["summary"]
    with st.container(border=True):
        if order.created:
            st.success(f"Pedido registrado! Protocolo **{order.protocol}**", icon="✅")
        else:
            st.info(f"Este mesmo pedido já estava registrado com o protocolo **{order.protocol}**. "
                    "Não criamos um pedido repetido.")
        st.write(f"**Status:** {order.status}. A confeitaria vai conferir a disponibilidade e o valor final "
                 f"e responder no WhatsApp {format_br_phone(request.whatsapp)}.")
        st.write("Este registro **ainda não confirma** o pedido nem o preço final.")
        link = order_wa_link(order, request, summary)
        if link:
            st.link_button("Avisar a confeitaria no WhatsApp", link, type="primary", width="stretch")
            st.caption("O botão abre o WhatsApp com o protocolo e o resumo já escritos. "
                       "A confeitaria só recebe depois que você tocar em **enviar**.")
        if st.button("Fazer outro pedido", key="ord_new"):
            st.session_state.pop("ord_done", None)
            st.rerun()


def _close_review() -> None:
    st.session_state.pop("ord_request", None)


@st.dialog("Revise o seu pedido", width="large", on_dismiss=_close_review)
def review_dialog(repo, products) -> None:
    request = st.session_state.get("ord_request")
    if request is None:
        st.rerun()
    summary = summarize(request, products)
    st.dataframe(pd.DataFrame([
        {"Produto": line.name, "Quantidade": f"{line.quantity} ({line.unit})", "Preço": line.price_label,
         "Subtotal estimado": format_brl(line.subtotal) if line.subtotal is not None else "Sob consulta"}
        for line in summary.lines
    ]), hide_index=True, width="stretch")
    st.markdown(f"**Total estimado:** {summary.total_label}")
    st.markdown(
        f"**Nome:** {request.customer_name}  \n"
        f"**WhatsApp:** {format_br_phone(request.whatsapp)}  \n"
        f"**Data desejada:** {request.delivery_date:%d/%m/%Y}  \n"
        f"**{request.fulfillment}**" + (f": {request.address}" if request.address else "") + "  \n"
        f"**Observações:** {request.notes or '—'}"
    )
    st.info(ORDER_NOTICE, icon="ℹ️")
    c1, c2 = st.columns(2)
    if c2.button("Voltar e editar", key="ord_back", width="stretch"):
        st.session_state.pop("ord_request", None)
        st.rerun()
    if c1.button("Confirmar pedido", key="ord_confirm", type="primary", width="stretch"):
        try:
            with st.spinner("Registrando o pedido..."):
                order = repo.create_order(request)
        except LeadValidationError as exc:
            st.error(str(exc))
        except (LeadPersistenceError, Exception) as exc:  # nunca mostra detalhes técnicos
            log.error("Falha ao registrar pedido: %s", type(exc).__name__)
            st.error("Não foi possível registrar o pedido agora. Nada foi gravado: tente de novo em instantes "
                     "ou fale com a confeitaria pelo WhatsApp.")
        else:
            st.session_state["ord_done"] = {"order": order, "request": request, "summary": summary}
            st.session_state.pop("ord_request", None)
            st.session_state["ord_nonce"] = _nonce() + 1  # limpa o formulário
            st.rerun()


# ---------------------------------------------------------------- página
st.title("🛒 Fazer pedido")
st.write("Já sabe o que quer? Escolha os produtos e as quantidades. Se ainda tiver dúvidas, "
         "peça um **orçamento** pelo catálogo.")
try:
    st.page_link("pages/public/catalog.py", label="← Voltar ao catálogo")
except Exception:
    st.markdown("[← Voltar ao catálogo](/)")

if "origin" not in st.session_state:
    st.session_state["origin"] = normalize_origin(st.query_params.get("origem") or st.query_params.get("utm_source"))

if st.session_state.get("ord_done"):
    render_done(st.session_state["ord_done"])

try:
    repo = _repository(settings.db_backend, str(settings.sqlite_path), settings.store_slug,
                       settings.supabase_url or "", (settings.supabase_key or "")[:12])
    products = [p for p in repo.list_products() if p.published]
except Exception as exc:
    log.error("Falha ao carregar produtos do pedido: %s", type(exc).__name__)
    _repository.clear()
    st.error("Os pedidos estão indisponíveis no momento. Tente novamente em alguns minutos.")
    st.stop()

available = [p for p in products if p.available]
if not available:
    st.warning("Nenhum produto disponível para pedido no momento.")
    st.stop()

by_slug = {p.slug: p for p in available}
initial = st.query_params.get("produto")
st.subheader("1. Produtos")
chosen = st.multiselect(
    f"Produtos * (até {MAX_ITEMS})", list(by_slug), max_selections=MAX_ITEMS,
    default=[initial] if initial in by_slug else None,
    format_func=lambda s: f"{by_slug[s].name} · {by_slug[s].price_label}", key=k("products"),
    placeholder="Escolha um ou mais produtos",
)
quantities = {}
for slug in chosen:
    p = by_slug[slug]
    c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
    c1.markdown(f"**{p.name}**  \n{p.price_label}" + (f" · ⏱️ {p.production_label}" if p.production_label else ""))
    quantities[slug] = c2.number_input(f"Quantidade ({p.unit})", min_value=p.min_qty, max_value=p.max_qty,
                                       value=p.min_qty, step=1, key=k(f"qty_{slug}"),
                                       help=f"Entre {p.min_qty} e {p.max_qty}.")

st.subheader("2. Entrega e contato")
name = st.text_input("Seu nome *", max_chars=80, key=k("name"))
phone = st.text_input("WhatsApp com DDD *", placeholder="(11) 99999-9999", max_chars=20, key=k("phone"))
today = date.today()
desired = st.date_input("Data desejada *", value=None, min_value=today,
                        max_value=today + timedelta(days=MAX_DAYS_AHEAD), format="DD/MM/YYYY", key=k("date"))
fulfillment = st.radio("Retirada ou entrega? *", FULFILLMENT_OPTIONS, horizontal=True, key=k("fulfillment"))
address = ""
if fulfillment == DELIVERY:
    address = st.text_area("Endereço de entrega *", max_chars=ADDRESS_MAX, key=k("address"),
                           placeholder="Rua, número, complemento, bairro e cidade",
                           help="A taxa e a disponibilidade de entrega são confirmadas pela confeitaria.")
notes = st.text_area("Observações", max_chars=NOTES_MAX, key=k("notes"),
                     placeholder="Sabores, recheios, tema, cores, frase no bolo...")
with st.expander("Como usamos seus dados"):
    st.write(PRIVACY_SHORT)
    _privacy_link("Ler o aviso de privacidade completo")
consent = st.checkbox("Concordo com o uso dos meus dados para o contato sobre este pedido. *", key=k("consent"))

if st.button("Revisar pedido", type="primary", key="ord_review", width="stretch"):
    form = {"customer_name": name, "whatsapp": phone, "delivery_date": desired, "fulfillment": fulfillment,
            "address": address, "notes": notes, "consent": consent, "origin": st.session_state.get("origin"),
            "items": [{"product_id": s, "quantity": q} for s, q in quantities.items()]}
    request, errors = validate_order(form, products, today)
    if errors:
        st.error("Confira os campos:\n\n" + "\n".join(f"- {m}" for m in errors.values()))
    else:
        st.session_state.pop("ord_done", None)
        st.session_state["ord_request"] = request

if st.session_state.get("ord_request"):
    review_dialog(repo, products)

st.caption(ORDER_NOTICE)
