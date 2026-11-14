"""Estúdio de Marketing: cria posts (Feed/Story) e legendas para o Instagram.

Acesso somente com a sessão administrativa válida (mesmo login do painel).
Não publica no Instagram: a confeiteira baixa a imagem e copia a legenda.
"""

import logging
from datetime import datetime, timezone
from io import BytesIO

import streamlit as st
from PIL import Image, UnidentifiedImageError

from components.navigation import admin_header
from config import load_settings
from services.auth_service import require_admin
from marketing.brand import using_brand_fonts
from services.dashboard_service import BRT
from marketing.caption_generator import (
    TEMPLATE_TYPES,
    TONES,
    default_post_texts,
    generate_caption,
    product_photo,
)
from marketing.store import MARKETING_STATUSES, MarketingError, PostDraft, get_marketing_store
from marketing.post_generator import FIT_MODES, FORMAT_LABELS, TEMPLATES, PostContent, render_post

log = logging.getLogger("doceflow.marketing")
settings = load_settings()
st.set_page_config(page_title=f"{settings.app_name} · Marketing", page_icon="📣", layout="wide")

MAX_UPLOAD_MB = 10
FIELD_LABELS = {"title": "título", "price": "preço", "cta": "chamada"}

repo = require_admin(settings)  # sem sessão válida, leva ao login
admin_header("Estúdio de Marketing · Instagram")

try:
    products = repo.list_products()
    store = get_marketing_store(settings, repo)
except Exception as exc:
    log.error("Falha ao abrir o estúdio: %s", type(exc).__name__)
    st.error("Não foi possível carregar os produtos agora. Tente novamente em instantes.")
    st.stop()
if not products:
    st.info("Cadastre produtos no painel para criar posts.")
    st.stop()

flash = st.session_state.pop("mk_flash", None)
if flash:
    getattr(st, flash[0])(flash[1])
if not using_brand_fonts():
    st.caption("ℹ️ Fontes da marca (Abril Fatface e Quicksand) não instaladas em assets/fonts: "
               "usando fontes do sistema com acentos.")

by_slug = {p.slug: p for p in products}
editor, preview = st.columns([1, 1], gap="large")

# ------------------------------------------------------------------ editor
with editor:
    st.subheader("1. Arte")
    slug = st.selectbox("Produto", list(by_slug), key="mk_product",
                        format_func=lambda s: by_slug[s].name + ("" if by_slug[s].available else " (indisponível)"))
    product = by_slug[slug]
    c1, c2 = st.columns(2)
    fmt = c1.radio("Formato", list(FORMAT_LABELS), format_func=FORMAT_LABELS.get, key="mk_format")
    template = c2.selectbox("Template", TEMPLATE_TYPES, format_func=lambda k: TEMPLATES[k]["nome"], key="mk_template")

    defaults = default_post_texts(product, template)
    suffix = f"{slug}_{template}"
    title = st.text_input("Título", value=defaults["title"], max_chars=120, key=f"mk_title_{suffix}")
    price = st.text_input("Preço", value=defaults["price"], max_chars=80, key=f"mk_price_{suffix}",
                          help="Mantenha 'A partir de': o valor final é confirmado no orçamento.")
    cta = st.text_input("Chamada para ação", value=defaults["cta"], max_chars=60, key=f"mk_cta_{suffix}")

    own_photo = product_photo(product)
    photo_options = (["produto"] if own_photo is not None else []) + ["enviar", "nenhuma"]
    photo_labels = {"produto": "Foto do produto", "enviar": "Enviar outra foto", "nenhuma": "Sem foto (usa o logo)"}
    photo_choice = st.radio("Foto", photo_options, format_func=photo_labels.get, horizontal=True,
                            key=f"mk_photo_{slug}")
    photo = own_photo if photo_choice == "produto" else None
    if photo_choice == "enviar":
        upload = st.file_uploader("Foto (JPG, PNG ou WEBP, até 10 MB)", type=["jpg", "jpeg", "png", "webp"],
                                  key="mk_upload")
        if upload is not None:
            if upload.size > MAX_UPLOAD_MB * 1024 * 1024:
                st.error(f"A foto passa de {MAX_UPLOAD_MB} MB.")
            else:
                try:
                    data = upload.getvalue()
                    Image.open(BytesIO(data)).verify()  # rejeita arquivo corrompido ou falso
                    photo = Image.open(BytesIO(data))
                except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
                    st.error("Não foi possível abrir essa imagem. Envie um JPG, PNG ou WEBP válido.")
    fit = st.radio("Enquadramento da foto", list(FIT_MODES), format_func=FIT_MODES.get, horizontal=True,
                   key="mk_fit", disabled=photo is None)

    st.subheader("2. Legenda")
    tone = st.radio("Tom", list(TONES), format_func=TONES.get, horizontal=True, key="mk_tone")
    link = st.text_input("Link da vitrine (opcional)", key="mk_link",
                         placeholder="https://seu-app.streamlit.app/?origem=instagram")
    caption_default = generate_caption(template, product, tone, link=link.strip() or None)
    caption = st.text_area("Legenda (edite à vontade)", value=caption_default, height=280, max_chars=2200,
                           key=f"mk_caption_{suffix}_{tone}_{hash(link)}")
    st.caption("Para copiar: use o ícone de cópia no quadro abaixo.")
    st.code(caption, language=None, wrap_lines=True)

# ------------------------------------------------------------------ prévia
with preview:
    st.subheader("3. Prévia")
    result = render_post(template, fmt, PostContent(title=title, price=price, cta=cta, photo=photo, fit=fit))
    for field in result.truncated:
        st.warning(f"O {FIELD_LABELS[field]} não coube inteiro e foi abreviado com '…'. Encurte o texto.")
    if result.photo_upscale > 2:
        tip = " Experimente 'Mostrar foto inteira'." if fit == "cover" else ""
        st.warning(f"A foto é pequena para esta área (ampliada {result.photo_upscale:.1f}×) e pode ficar "
                   f"borrada. Use uma foto de maior resolução.{tip}")
    st.image(result.png, caption=f"{FORMAT_LABELS[fmt]} · {TEMPLATES[template]['nome']}", width="stretch")
    st.download_button("Baixar PNG", result.png, file_name=f"kika-{template}-{fmt}-{slug}.png", mime="image/png",
                       type="primary", width="stretch")

    status = st.selectbox("Status ao salvar", MARKETING_STATUSES, key="mk_status")
    if st.button("Salvar no histórico", width="stretch", key="mk_save"):
        draft = PostDraft(produto_id=product.id, produto_nome=product.name, template=template, formato=fmt,
                          titulo=title, preco_texto=price, cta=cta, tom=tone, legenda=caption, status=status)
        try:
            store.save(draft, result.png)
        except MarketingError as exc:
            st.error(str(exc))
        except Exception as exc:
            log.error("Falha ao salvar post: %s", type(exc).__name__)
            st.error("Não foi possível salvar agora. Nada foi gravado.")
        else:
            st.session_state["mk_flash"] = ("success", f"Post salvo como **{status}**.")
            st.rerun()

# ------------------------------------------------------------------ histórico
st.divider()
st.subheader("Posts salvos")
try:
    posts = store.list()
except MarketingError as exc:
    st.warning(str(exc))
    posts = []
if not posts:
    st.write("Nenhum post salvo ainda.")
for post in posts:
    created = datetime.fromisoformat(str(post["created_at"]).replace("Z", "+00:00"))
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    label = (f"{post['status']} · {post['produto_nome']} · {TEMPLATES[post['template']]['nome']} · "
             f"{FORMAT_LABELS[post['formato']]} · {created.astimezone(BRT):%d/%m/%Y %H:%M}")
    with st.expander(label):
        left, right = st.columns([1, 2])
        try:
            image = store.image(post["imagem_path"]) if post.get("imagem_path") else None
        except MarketingError:
            image = None
        with left:
            if image:
                st.image(image, width="stretch")
                st.download_button("Baixar PNG", image, file_name=f"kika-post-{post['id'][:8]}.png",
                                   mime="image/png", key=f"dl_{post['id']}")
            else:
                st.caption("Imagem indisponível.")
        with right:
            new_caption = st.text_area("Legenda", value=post["legenda"], height=200, max_chars=2200,
                                       key=f"cap_{post['id']}")
            new_status = st.selectbox("Status", MARKETING_STATUSES,
                                      index=MARKETING_STATUSES.index(post["status"]), key=f"st_{post['id']}")
            if st.button("Salvar alterações", key=f"upd_{post['id']}"):
                draft = PostDraft(produto_id=post.get("produto_id"), produto_nome=post["produto_nome"],
                                  template=post["template"], formato=post["formato"], titulo=post["titulo"],
                                  preco_texto=post["preco_texto"], cta=post["cta"], tom=post["tom"],
                                  legenda=new_caption, status=new_status)
                try:
                    store.update(post["id"], draft)
                except MarketingError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["mk_flash"] = ("success", "Alterações salvas.")
                    st.rerun()
