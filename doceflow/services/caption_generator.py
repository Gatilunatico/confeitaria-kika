"""Geração de legendas para Instagram a partir dos templates (templates/*.json).

Regras: o preço é sempre "a partir de" (o valor final é confirmado pela
confeitaria), e a legenda nunca promete disponibilidade.
"""

from __future__ import annotations

import json
from functools import lru_cache

from config import BASE_DIR
from services.catalog import Product, format_brl

TEMPLATES_DIR = BASE_DIR / "templates"
TEMPLATE_TYPES = ("promocao", "produto", "novidade")


@lru_cache(maxsize=None)
def load_template(kind: str) -> dict:
    if kind not in TEMPLATE_TYPES:
        raise ValueError(f"Template desconhecido: {kind}")
    return json.loads((TEMPLATES_DIR / f"{kind}.json").read_text(encoding="utf-8"))


def _price_text(product: Product) -> str:
    if product.price is None:
        return "Preço sob consulta"
    return f"a partir de {format_brl(product.price)} / {product.unit}"


def generate_caption(kind: str, product: Product, extra: str = "", link: str | None = None) -> str:
    """Legenda pronta para colar no Instagram."""
    template = load_template(kind)
    values = {"produto": product.name, "descricao": product.description.split(".")[0], "preco": _price_text(product)}
    lines = [template["titulo"].format(**values), "", template["chamada"].format(**values)]
    if extra.strip():
        lines += ["", extra.strip()]
    if link:
        lines += ["", f"Orçamento: {link}"]
    lines += ["", " ".join(template["hashtags"])]
    return "\n".join(lines)
