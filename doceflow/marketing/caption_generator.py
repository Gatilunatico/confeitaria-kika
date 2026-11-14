"""Legendas para Instagram a partir dos dados do produto e dos templates (templates/*.json).

Tons: amigável, promocional e elegante. Toda legenda tem chamada para ação e
hashtags. Regras: o preço é sempre "a partir de" (o valor final é confirmado
pela confeitaria) e a legenda nunca promete disponibilidade.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image

from config import BASE_DIR
from marketing.brand import INSTAGRAM_HANDLE
from services.product_service import Product, format_brl

TEMPLATES_DIR = BASE_DIR / "marketing" / "templates"
TEMPLATE_TYPES = ("produto", "promocao", "novidade")
TONES = {"amigavel": "Amigável", "promocional": "Promocional", "elegante": "Elegante"}

CATEGORY_HASHTAGS = {
    "Bolos": ["#bolodeaniversario", "#bolosdecorados", "#bolodefesta"],
    "Docinhos": ["#docinhos", "#brigadeirogourmet", "#docesdefesta"],
    "Personalizados com Tag": ["#docespersonalizados", "#lembrancinhas", "#festapersonalizada"],
    "Personalizados com Etiqueta": ["#docespersonalizados", "#lembrancinhas", "#festapersonalizada"],
    "Personalizados em Pasta Americana": ["#pastaamericana", "#docespersonalizados", "#festainfantil"],
    "Doces Finos": ["#docesfinos", "#casamento", "#bemcasado"],
}
CTA_BY_TONE = {
    "amigavel": "Me chama no WhatsApp pelo link da bio e faça seu orçamento! 💬",
    "promocional": "Peça já seu orçamento pelo link da bio: as datas estão acabando!",
    "elegante": "Solicite seu orçamento pelo link da bio.",
}
PRICE_NOTE = "Valor final confirmado no orçamento."


@lru_cache(maxsize=None)
def load_template(kind: str) -> dict:
    if kind not in TEMPLATE_TYPES:
        raise ValueError(f"Template desconhecido: {kind}")
    return json.loads((TEMPLATES_DIR / f"{kind}.json").read_text(encoding="utf-8"))


def price_text(product: Product) -> str:
    if product.price is None:
        return "Preço sob consulta"
    return f"A partir de {format_brl(product.price)} / {product.unit}"


def default_post_texts(product: Product, kind: str) -> dict:
    """Título, preço e chamada sugeridos para a arte (editáveis na tela)."""
    template = load_template(kind)
    return {"title": template["titulo"].format(produto=product.name), "price": price_text(product),
            "cta": template["cta"]}


def product_photo(product: Product) -> Image.Image | None:
    """Foto real do produto (PNG/JPG/WEBP). Ilustrações SVG não contam como foto."""
    path = product.image_path
    if not path or Path(path).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return None
    return Image.open(path)


def suggest_hashtags(product: Product, kind: str, limit: int = 10) -> list[str]:
    tags = list(load_template(kind)["hashtags"])
    tags += CATEGORY_HASHTAGS.get(product.category, [])
    name_tag = "#" + re.sub(r"[^a-z0-9]", "", _ascii(product.name.lower()))
    if 3 < len(name_tag) <= 30:
        tags.append(name_tag)
    tags += ["#encomendas", "#docesartesanais"]
    return list(dict.fromkeys(tags))[:limit]


def _ascii(text: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def _first_sentence(description: str) -> str:
    text = description.split(" Informe")[0].strip()
    return text if text.endswith(".") else (text + "." if text else "")


def generate_caption(kind: str, product: Product, tone: str = "amigavel", extra: str = "",
                     link: str | None = None) -> str:
    """Legenda pronta para revisar, editar e copiar."""
    if tone not in TONES:
        raise ValueError(f"Tom desconhecido: {tone}")
    template = load_template(kind)
    parts = [template["abertura"][tone].format(produto=product.name)]
    details = _first_sentence(product.description)
    if details:
        parts.append(details)
    parts.append(f"💰 {price_text(product)}. {PRICE_NOTE}")
    if extra.strip():
        parts.append(extra.strip())
    cta = CTA_BY_TONE[tone]
    if link:
        cta += f"\n🔗 {link}"
    parts.append(cta)
    parts.append(INSTAGRAM_HANDLE)
    parts.append(" ".join(suggest_hashtags(product, kind)))
    return "\n\n".join(parts)
