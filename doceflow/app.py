"""DoceFlow: vitrine pública (catálogo + solicitação de orçamento)."""

import logging
from datetime import date, timedelta

import streamlit as st

from config import BASE_DIR, load_settings
from database import DatabaseConfigError, Repository, get_repository
from services.catalog import Product, find_product, list_categories
from services.leads import (
    FULFILLMENT_OPTIONS,
    MAX_DAYS_AHEAD,
    NOTES_MAX,
    Lead,
    LeadValidationError,
    format_br_phone,
    normalize_origin,
    validate_lead,
)
from services.whatsapp import lead_wa_link

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("doceflow.app")

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

PRICE_NOTICE = (
    "Os preços são iniciais ou estimados. O valor final e a disponibilidade para a data "
    "são confirmados pela confeitaria após a análise do pedido."
)
PRIVACY_SHORT = (
    "Usamos seu nome e WhatsApp apenas para responder este orçamento. Não pedimos endereço, "
    "CPF nem e-mail. Seus dados não ficam públicos e você pode pedir a exclusão a qualquer momento."
)

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
def render_confirmation(last: Lead) -> None:
    """Confirmação do lead gravado. Usada no diálogo (logo após enviar) e no topo da página."""
    if last.created:
        st.success(f"Solicitação registrada! Protocolo **{last.protocol}**")
    else:
        st.info(
            f"Este mesmo pedido já estava registrado com o protocolo **{last.protocol}**. "
            "Não criamos uma solicitação repetida."
        )
    st.write(
        f"**{last.product_name}**: {last.quantity} ({last.unit}) para "
        f"{last.desired_date:%d/%m/%Y}, {last.fulfillment.lower()}."
    )
    link = lead_wa_link(last)
    if link:
        st.link_button("Abrir conversa no WhatsApp", link, type="primary", width="stretch")
        st.caption(
            "O botão abre o WhatsApp com a mensagem do pedido já escrita. "
            "A confeitaria só recebe depois que você tocar em **enviar** no WhatsApp."
        )
    else:
        st.warning("O contato por WhatsApp da confeitaria ainda não está configurado.")
    phone = st.session_state.get("last_phone")
    contact = f" no WhatsApp {format_br_phone(phone)}" if phone else ""
    st.write(
        f"A confeitaria vai conferir a disponibilidade e responder{contact}. "
        "Esta solicitação ainda **não confirma** o pedido nem o preço."
    )


last: Lead | None = st.session_state.get("last_lead")
if last is not None and not st.session_state.get("dialog_confirmed"):
    with st.container(border=True):
        render_confirmation(last)
        if st.button("Fazer nova solicitação", key="new_request"):
            st.session_state.pop("last_lead", None)
            st.rerun()


# ---------- Formulário (diálogo) ----------
# O produto escolhido fica em session_state["dialog_product"] para o diálogo
# continuar aberto entre interações; fechar no "X" limpa o estado.
def _open_dialog(product_slug: str) -> None:
    st.session_state["dialog_product"] = product_slug
    st.session_state.pop("dialog_confirmed", None)  # novo pedido sempre abre o formulário


def _close_dialog() -> None:
    st.session_state.pop("dialog_product", None)
    st.session_state.pop("dialog_confirmed", None)


@st.dialog("Solicitar orçamento", on_dismiss=_close_dialog)
def quote_dialog(product_slug: str) -> None:
    # Depois de gravar, a confirmação aparece aqui mesmo: no celular a página
    # fica rolada no catálogo e a confirmação do topo ficaria fora da tela.
    if st.session_state.get("dialog_confirmed") and st.session_state.get("last_lead"):
        render_confirmation(st.session_state["last_lead"])
        if st.button("Fechar", key="close_confirmation", width="stretch"):
            _close_dialog()
            st.rerun()
        return

    available = [p for p in products if p.available]
    if repo is None or not available:
        st.error("No momento não há produtos disponíveis para orçamento. Tente novamente mais tarde.")
        return
    slugs = [p.slug for p in available]
    index = slugs.index(product_slug) if product_slug in slugs else 0

    selected = st.selectbox(
        "Produto desejado *", slugs, index=index,
        format_func=lambda s: find_product(available, s).name, key="f_product",
    )
    product = find_product(available, selected)
    st.caption(f"{product.price_label}. {PRICE_NOTICE}")

    name = st.text_input("Seu nome *", max_chars=80, key="f_name")
    phone = st.text_input("WhatsApp com DDD *", placeholder="(11) 99999-9999", max_chars=20, key="f_phone")
    quantity = st.number_input(
        f"Quantidade ({product.unit}) *", min_value=1, max_value=1000, value=product.min_qty, step=1,
        key=f"f_qty_{product.slug}", help=f"Entre {product.min_qty} e {product.max_qty}.",
    )
    today = date.today()
    desired = st.date_input(
        "Data desejada *", value=None, min_value=today, max_value=today + timedelta(days=MAX_DAYS_AHEAD),
        format="DD/MM/YYYY", key="f_date",
    )
    fulfillment = st.radio("Retirada ou entrega? *", FULFILLMENT_OPTIONS, horizontal=True, key="f_fulfillment")
    notes = st.text_area(
        "Observações e personalização", placeholder="Sabor, recheio, tema, cores, frase no bolo...",
        max_chars=NOTES_MAX, key="f_notes",
    )
    with st.expander("Como usamos seus dados"):
        st.write(PRIVACY_SHORT)
        st.page_link("pages/privacidade.py", label="Ler o aviso de privacidade completo")
    consent = st.checkbox(
        f"Autorizo a {settings.store_name} a usar meu nome e WhatsApp apenas para responder este orçamento. *",
        key="f_consent",
    )
    st.caption("\\* Campos obrigatórios.")

    if st.button("Enviar solicitação", type="primary", width="stretch"):
        request, errors = validate_lead(
            {
                "customer_name": name, "whatsapp": phone, "product_id": selected, "quantity": quantity,
                "desired_date": desired, "fulfillment": fulfillment, "notes": notes, "consent": consent,
                "origin": st.session_state.get("origin"),
            },
            products,
        )
        if errors:
            st.error("Corrija estes campos do formulário:\n\n" + "\n".join(f"- {msg}" for msg in errors.values()))
            return
        try:
            lead = repo.create_lead(request)  # grava ANTES de liberar o link do WhatsApp
        except LeadValidationError as exc:
            st.error(str(exc))
            return
        except Exception as exc:  # banco fora do ar, rede etc.: nunca mostrar sucesso
            log.error("Falha ao registrar lead: %s", type(exc).__name__)
            st.error(
                "Não conseguimos registrar sua solicitação agora e nada foi enviado à confeitaria. "
                "Tente novamente em instantes."
            )
            return
        st.session_state["last_lead"] = lead
        st.session_state["last_phone"] = request.whatsapp
        st.session_state["dialog_confirmed"] = True  # mostra a confirmação no próprio diálogo
        st.rerun()


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
            with col, st.container(border=True):
                if product.image_path:
                    st.image(product.image_path, width="stretch")
                st.badge(product.category, color="primary")
                st.markdown(f"**{product.name}**")
                st.caption(product.description)
                st.markdown(f'<p class="df-price">{product.price_label}</p>', unsafe_allow_html=True)
                if product.available:
                    st.button(
                        "Solicitar orçamento", key=f"req_{product.slug}", type="primary", width="stretch",
                        on_click=_open_dialog, args=(product.slug,),
                    )
                else:
                    st.button("Indisponível no momento", key=f"req_{product.slug}", disabled=True, width="stretch")
                    st.caption("Este produto está temporariamente indisponível. Veja outras opções do catálogo.")

if st.session_state.get("dialog_product"):
    quote_dialog(st.session_state["dialog_product"])

st.divider()
st.page_link("pages/privacidade.py", label="Aviso de privacidade")
st.caption(f"{settings.store_name} · Vitrine digital por {settings.app_name}")
