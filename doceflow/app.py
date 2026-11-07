"""DoceFlow: vitrine pública (catálogo + solicitação de orçamento)."""

from datetime import date, timedelta

import streamlit as st

from config import BASE_DIR, load_settings
from services.catalog import Product, get_product, list_categories, list_products
from services.quotes import (
    FULFILLMENT_OPTIONS,
    MAX_DAYS_AHEAD,
    NOTES_MAX,
    DuplicateQuoteError,
    InMemoryQuoteStore,
    format_br_phone,
    validate_quote,
)
from services.whatsapp import build_wa_link

settings = load_settings()
st.set_page_config(page_title=settings.store_name, page_icon="🧁", layout="centered")

st.markdown(
    """
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
    """,
    unsafe_allow_html=True,
)

if "quote_store" not in st.session_state:
    st.session_state["quote_store"] = InMemoryQuoteStore()
store: InMemoryQuoteStore = st.session_state["quote_store"]

PRICE_NOTICE = (
    "Os preços são iniciais ou estimados. O valor final e a disponibilidade para a data "
    "são confirmados pela confeitaria após a análise do pedido."
)


# ---------- Cabeçalho ----------
logo = BASE_DIR / "assets" / "images" / "logo-kika-cakes.png"
col_logo, col_text = st.columns([1, 2.4], vertical_alignment="center")
with col_logo:
    if logo.exists():
        st.image(str(logo), width=170)
with col_text:
    st.title(settings.store_name)
    st.write("Bolos, cupcakes e doces artesanais feitos com carinho para a sua festa.")
    st.markdown('<a class="df-cta" href="#catalogo" target="_self">Ver catálogo e pedir orçamento</a>',
                unsafe_allow_html=True)


# ---------- Confirmação da última solicitação ----------
last = st.session_state.get("last_quote")
if last is not None:
    with st.container(border=True):
        st.success(f"Solicitação enviada! Protocolo **{last.protocol}**")
        st.write(
            f"**{last.product_name}**: {last.quantity} ({last.unit}) para "
            f"{last.desired_date:%d/%m/%Y}, {last.fulfillment.lower()}."
        )
        st.write(
            f"A confeitaria vai conferir a disponibilidade e enviar o valor final pelo WhatsApp "
            f"{format_br_phone(last.whatsapp)}. Este envio ainda **não confirma** o pedido nem o preço."
        )
        if settings.whatsapp_number:
            msg = (
                f"Olá! Enviei a solicitação de orçamento {last.protocol}: {last.product_name}, "
                f"{last.quantity} ({last.unit}), para {last.desired_date:%d/%m/%Y}."
            )
            try:
                st.link_button("Avisar a confeitaria no WhatsApp", build_wa_link(settings.whatsapp_number, msg))
            except ValueError:
                pass
        if st.button("Fazer nova solicitação"):
            st.session_state.pop("last_quote", None)
            st.rerun()


# ---------- Formulário (diálogo) ----------
# O produto escolhido fica em session_state["dialog_product"] para o diálogo
# continuar aberto entre interações; fechar no "X" limpa o estado.
def _open_dialog(product_id: str) -> None:
    st.session_state["dialog_product"] = product_id


def _close_dialog() -> None:
    st.session_state.pop("dialog_product", None)


@st.dialog("Solicitar orçamento", on_dismiss=_close_dialog)
def quote_dialog(product_id: str) -> None:
    available = [p for p in list_products() if p.available]
    if not available:
        st.error("No momento não há produtos disponíveis para orçamento. Tente novamente mais tarde.")
        return
    ids = [p.id for p in available]
    index = ids.index(product_id) if product_id in ids else 0

    selected_id = st.selectbox(
        "Produto desejado *", ids, index=index, format_func=lambda i: get_product(i).name, key="f_product"
    )
    product: Product = get_product(selected_id)
    st.caption(f"{product.price_label}. {PRICE_NOTICE}")

    name = st.text_input("Seu nome *", max_chars=80, key="f_name")
    phone = st.text_input("WhatsApp com DDD *", placeholder="(11) 99999-9999", max_chars=20, key="f_phone")
    quantity = st.number_input(
        f"Quantidade ({product.unit}) *",
        min_value=1,
        max_value=1000,
        value=product.min_qty,
        step=1,
        key=f"f_qty_{product.id}",
        help=f"Entre {product.min_qty} e {product.max_qty}.",
    )
    today = date.today()
    desired = st.date_input(
        "Data desejada *",
        value=None,
        min_value=today,
        max_value=today + timedelta(days=MAX_DAYS_AHEAD),
        format="DD/MM/YYYY",
        key="f_date",
    )
    fulfillment = st.radio("Retirada ou entrega? *", FULFILLMENT_OPTIONS, horizontal=True, key="f_fulfillment")
    notes = st.text_area(
        "Observações e personalização",
        placeholder="Sabor, recheio, tema, cores, frase no bolo...",
        max_chars=NOTES_MAX,
        key="f_notes",
    )
    consent = st.checkbox(
        f"Autorizo a {settings.store_name} a usar meu nome e WhatsApp apenas para responder este orçamento. *",
        key="f_consent",
    )
    st.caption("\\* Campos obrigatórios. Não pedimos endereço nem documentos nesta etapa.")

    if st.button("Enviar solicitação", type="primary", width="stretch"):
        quote, errors = validate_quote(
            {
                "customer_name": name,
                "whatsapp": phone,
                "product_id": selected_id,
                "quantity": quantity,
                "desired_date": desired,
                "fulfillment": fulfillment,
                "notes": notes,
                "consent": consent,
            }
        )
        if errors:
            st.error("Confira os campos abaixo:\n\n" + "\n".join(f"- {msg}" for msg in errors.values()))
            return
        try:
            store.add(quote)
        except DuplicateQuoteError as dup:
            st.warning(
                f"Você já enviou esta mesma solicitação (protocolo {dup.existing.protocol}). "
                "Não é preciso enviar de novo."
            )
            return
        st.session_state["last_quote"] = quote
        _close_dialog()
        st.rerun()


# ---------- Catálogo ----------
st.header("Catálogo", anchor="catalogo")
st.info(PRICE_NOTICE, icon="ℹ️")

products = list_products()
category = st.pills("Categoria", ["Todos", *list_categories(products)], default="Todos", key="category")
category = category or "Todos"
visible = [p for p in products if category == "Todos" or p.category == category]

if not visible:
    st.warning("Nenhum produto nesta categoria no momento.")

for row_start in range(0, len(visible), 2):
    cols = st.columns(2)
    for col, product in zip(cols, visible[row_start : row_start + 2]):
        with col, st.container(border=True):
            st.image(product.image_path, width="stretch")
            st.badge(product.category, color="primary")
            st.markdown(f"**{product.name}**")
            st.caption(product.description)
            st.markdown(f'<p class="df-price">{product.price_label}</p>', unsafe_allow_html=True)
            if product.available:
                st.button(
                    "Solicitar orçamento",
                    key=f"req_{product.id}",
                    type="primary",
                    width="stretch",
                    on_click=_open_dialog,
                    args=(product.id,),
                )
            else:
                st.button("Indisponível no momento", key=f"req_{product.id}", disabled=True, width="stretch")
                st.caption("Este produto está temporariamente indisponível. Veja outras opções do catálogo.")

if st.session_state.get("dialog_product"):
    quote_dialog(st.session_state["dialog_product"])

st.divider()
if settings.whatsapp_number:
    try:
        st.link_button(
            "Dúvidas? Fale no WhatsApp",
            build_wa_link(settings.whatsapp_number, "Olá! Vim pelo catálogo e tenho uma dúvida."),
        )
    except ValueError:
        pass
st.caption(f"{settings.store_name} · Vitrine digital por {settings.app_name}")
