"""Gestão de produtos: lista, visualização, edição, fotos, publicação, exclusão e cadastro.

Toda operação passa pelo repositório da administradora autenticada (require_admin).
No Supabase, quem garante a permissão é o banco (RLS, Storage e migrações 005/006/009);
a tela só organiza o trabalho e dá retorno rápido.
"""

import logging

import pandas as pd
import streamlit as st

from components.data_table import show_table
from components.image_manager import image_manager
from components.navigation import admin_header, flash
from components.product_card import inject_storefront_css, render_product_card
from components.product_form import product_form_fields
from config import load_settings
from services.auth_service import require_admin
from services.product_service import PRICE_ON_REQUEST, validate_product
from services.quote_service import LeadValidationError

log = logging.getLogger("doceflow.admin")
settings = load_settings()
st.set_page_config(page_title=f"{settings.app_name} · Produtos", page_icon="🧁", layout="wide")
repo = require_admin(settings)
admin_header("Produtos")
inject_storefront_css()


def _days(days: int | None) -> str:
    if days is None:
        return "não informado"
    return "pronta entrega" if days == 0 else f"cerca de {days} dia(s)"


def _show_errors(errors: dict) -> None:
    st.error("Confira os campos:\n\n" + "\n".join(f"- {m}" for m in errors.values()))


def _save(action, success: str, failure: str) -> bool:
    try:
        action()
    except LeadValidationError as exc:
        st.error(str(exc))
    except Exception as exc:
        log.error("%s: %s", failure, type(exc).__name__)
        st.error(f"{failure} Nada foi alterado.")
    else:
        flash("success", success)
        return True
    return False


try:
    products = repo.list_products()
except Exception as exc:
    log.error("Falha ao listar produtos: %s", type(exc).__name__)
    st.error("Não foi possível carregar os produtos agora.")
    products = []

st.caption("As alterações aparecem na vitrine na próxima vez que a página for carregada.")
if products:
    show_table(pd.DataFrame([
        {
            "Produto": p.name,
            "Categoria": p.category,
            "Preço na vitrine": p.price_label,
            "Na vitrine": "Sim" if p.published else "Não",
            "Disponível": "Sim" if p.available else "Não",
            "Destaque": "Sim" if p.featured else "Não",
            "Foto": "Enviada" if p.photo else ("Padrão" if p.image_path else "Sem foto"),
            "Quantidade": f"{p.min_qty} a {p.max_qty} ({p.unit})",
            "Produção": f"{p.production_days} dia(s)" if p.production_days is not None else "—",
            "Ordem": p.order,
        }
        for p in products
    ]))

    st.subheader("Gerenciar produto")
    by_pid = {p.id: p for p in products}
    if "select_next" in st.session_state:  # produto recém-cadastrado (ver o fim da página)
        st.session_state["sel_product"] = st.session_state.pop("select_next")
        st.session_state["product_tab"] = "Fotos"  # próximo passo natural: enviar as fotos
    if st.session_state.get("sel_product") not in by_pid:
        st.session_state.pop("sel_product", None)  # produto excluído ou de outra sessão
    pid = st.selectbox("Produto", list(by_pid), format_func=lambda i: by_pid[i].name, key="sel_product")
    product = by_pid[pid]
    # key + on_change: a aba aberta continua aberta depois de salvar, enviar ou remover fotos
    tab_view, tab_edit, tab_photos, tab_delete = st.tabs(["Visualizar", "Editar", "Fotos", "Excluir"],
                                                         key="product_tab", on_change="rerun")

    # ---------------------------------------------------------------- visualizar / publicar
    with tab_view:
        c_card, c_info = st.columns([1, 1.3])
        with c_card:
            st.caption("Como aparece na vitrine")
            render_product_card(product, None, key_prefix="preview", preview=True)
        with c_info:
            if product.published:
                st.success("Publicado: aparece na vitrine.", icon="✅")
            else:
                st.warning("Não publicado: visitantes não veem este produto.", icon="🙈")
            st.markdown(
                f"- **Disponível para orçamento:** {'sim' if product.available else 'não'}\n"
                f"- **Destaque:** {'sim' if product.featured else 'não'}\n"
                f"- **Quantidade:** {product.min_qty} a {product.max_qty} ({product.unit})\n"
                f"- **Tempo de produção:** {_days(product.production_days)}"
            )
            label = "Despublicar (tirar da vitrine)" if product.published else "Publicar na vitrine"
            if st.button(label, key=f"toggle_pub_{pid}", type="secondary" if product.published else "primary"):
                new_state = not product.published
                done = _save(lambda: repo.update_product(pid, {"published": new_state}),
                             f"**{product.name}** {'publicado' if new_state else 'despublicado'}.",
                             "Não foi possível alterar a publicação agora.")
                if done:
                    st.rerun()

    # ---------------------------------------------------------------- editar
    with tab_edit:
        with st.form(f"edit_{pid}"):
            values = product_form_fields(f"edit_{pid}", product)
            save = st.form_submit_button("Salvar produto", type="primary")
        if save:
            data, errors = validate_product(values, editing=True)
            if errors:
                _show_errors(errors)
            elif _save(lambda: repo.update_product(pid, data), f"Produto **{data['name']}** atualizado.",
                       "Não foi possível salvar o produto agora."):
                st.rerun()

    # ---------------------------------------------------------------- fotos
    with tab_photos:
        image_manager(repo, product)

    # ---------------------------------------------------------------- excluir
    with tab_delete:
        st.warning(
            "A exclusão apaga o produto e todas as fotos dele e **não pode ser desfeita**. "
            "Produtos com orçamentos ou pedidos registrados não podem ser excluídos: "
            "para tirá-los da vitrine, use **Despublicar**.", icon="⚠️")
        confirm = st.checkbox(f"Confirmo que quero excluir **{product.name}**", key=f"del_confirm_{pid}")
        if st.button("Excluir produto", key=f"del_{pid}", disabled=not confirm):
            if _save(lambda: repo.delete_product(pid), f"Produto **{product.name}** excluído.",
                     "Não foi possível excluir o produto agora."):
                st.rerun()

with st.expander("Cadastrar novo produto", expanded=not products):
    with st.form("new_product", clear_on_submit=False):
        values = product_form_fields("new")
        create = st.form_submit_button("Cadastrar produto", type="primary")
    if create:
        data, errors = validate_product(values, existing_slugs={p.slug for p in products})
        if data.get("price_type") == PRICE_ON_REQUEST:
            data["price"] = None
        if errors:
            _show_errors(errors)
        else:
            created: list[str] = []
            if _save(lambda: created.append(repo.create_product(data)),
                     f"Produto **{data['name']}** cadastrado. Agora envie as fotos na aba **Fotos**.",
                     "Não foi possível cadastrar o produto agora."):
                if created and created[0]:
                    st.session_state["select_next"] = created[0]  # já abre o produto novo
                st.rerun()
