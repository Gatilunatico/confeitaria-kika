"""Gestão de produtos: lista, edição e cadastro (preços e disponibilidade)."""

import logging

import pandas as pd
import streamlit as st

from components.data_table import show_table
from components.navigation import admin_header, flash
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
            "Disponível": "Sim" if p.available else "Não",
            "Quantidade": f"{p.min_qty} a {p.max_qty} ({p.unit})",
            "Ordem": p.order,
        }
        for p in products
    ]))

    st.subheader("Editar produto")
    by_pid = {p.id: p for p in products}
    pid = st.selectbox("Produto", list(by_pid), format_func=lambda i: by_pid[i].name, key="sel_product")
    with st.form(f"edit_{pid}"):
        values = product_form_fields(f"edit_{pid}", by_pid[pid])
        save = st.form_submit_button("Salvar produto", type="primary")
    if save:
        data, errors = validate_product(values, editing=True)
        if errors:
            st.error("Confira os campos:\n\n" + "\n".join(f"- {m}" for m in errors.values()))
        else:
            try:
                repo.update_product(pid, data)
            except LeadValidationError as exc:
                st.error(str(exc))
            except Exception as exc:
                log.error("Falha ao salvar produto: %s", type(exc).__name__)
                st.error("Não foi possível salvar o produto agora. Nada foi alterado.")
            else:
                flash("success", f"Produto **{data['name']}** atualizado.")
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
            st.error("Confira os campos:\n\n" + "\n".join(f"- {m}" for m in errors.values()))
        else:
            try:
                repo.create_product(data)
            except LeadValidationError as exc:
                st.error(str(exc))
            except Exception as exc:
                log.error("Falha ao cadastrar produto: %s", type(exc).__name__)
                st.error("Não foi possível cadastrar o produto agora.")
            else:
                flash("success", f"Produto **{data['name']}** cadastrado.")
                st.rerun()
