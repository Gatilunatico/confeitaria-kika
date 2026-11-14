"""Campos do formulário de cadastro/edição de produto (área administrativa)."""

import streamlit as st

from services.product_service import PRICE_TYPE_LABELS, PRICE_TYPES, available_images

NO_IMAGE = "(sem imagem)"


def product_form_fields(prefix: str, product=None) -> dict:
    """Desenha os campos (dentro de um st.form) e devolve os valores digitados."""
    images = [NO_IMAGE, *available_images()]
    c1, c2 = st.columns(2)
    values = {
        "name": c1.text_input("Nome *", value=product.name if product else "", max_chars=120, key=f"{prefix}_name"),
        "category": c2.text_input("Categoria *", value=product.category if product else "", max_chars=60,
                                  key=f"{prefix}_cat"),
    }
    values["description"] = st.text_area("Descrição", value=product.description if product else "", max_chars=500,
                                         key=f"{prefix}_desc")
    c3, c4, c5 = st.columns(3)
    values["price_type"] = c3.selectbox(
        "Tipo de preço *", PRICE_TYPES, format_func=PRICE_TYPE_LABELS.get,
        index=PRICE_TYPES.index(product.price_type) if product else 0, key=f"{prefix}_ptype",
    )
    values["price"] = c4.number_input(
        "Preço (R$)", min_value=0.0, step=1.0, format="%.2f",
        value=float(product.price) if product and product.price is not None else 0.0, key=f"{prefix}_price",
        help="Ignorado quando o tipo é 'Sob consulta'. O preço exibido é sempre inicial ou estimado.",
    )
    values["unit"] = c5.text_input("Unidade *", value=product.unit if product else "", max_chars=40,
                                   placeholder="kg, unidade, caixa com 6", key=f"{prefix}_unit")
    c6, c7, c8, c9 = st.columns(4)
    values["min_qty"] = c6.number_input("Qtd. mínima", min_value=1, step=1,
                                        value=product.min_qty if product else 1, key=f"{prefix}_min")
    values["max_qty"] = c7.number_input("Qtd. máxima", min_value=1, step=1,
                                        value=product.max_qty if product else 50, key=f"{prefix}_max")
    values["order"] = c8.number_input("Ordem na vitrine", min_value=0, step=1,
                                      value=product.order if product else 0, key=f"{prefix}_order")
    current_image = product.image if product and product.image in images else NO_IMAGE
    image = c9.selectbox("Imagem", images, index=images.index(current_image), key=f"{prefix}_img")
    values["image"] = None if image == NO_IMAGE else image
    values["available"] = st.checkbox("Disponível para orçamento", value=product.available if product else True,
                                      key=f"{prefix}_avail")
    return values
