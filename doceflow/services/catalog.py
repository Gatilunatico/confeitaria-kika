"""Modelo de produto do catálogo e dados iniciais (seed) de exemplo.

Os produtos exibidos na vitrine vêm do banco (tabela `produtos`) pelo
repositório em `database.py`. `SEED_PRODUCTS` só alimenta o SQLite local e
espelha `supabase/seed.sql`.

Preços são sempre INICIAIS ou ESTIMADOS: o valor final depende de tamanho,
recheio e personalização e é confirmado pela confeitaria.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from config import BASE_DIR

IMAGES_DIR = BASE_DIR / "assets" / "images" / "produtos"

PRICE_FROM = "a_partir_de"  # "a partir de R$ X"
PRICE_ESTIMATED = "estimado"  # "cerca de R$ X"
PRICE_ON_REQUEST = "sob_consulta"  # sem preço exibido
PRICE_TYPES = (PRICE_FROM, PRICE_ESTIMATED, PRICE_ON_REQUEST)


@dataclass(frozen=True)
class Product:
    slug: str
    name: str
    category: str
    description: str
    unit: str  # unidade da quantidade: "kg", "caixa com 6", "unidade"...
    price: float | None
    price_type: str
    available: bool
    image: str | None
    min_qty: int = 1
    max_qty: int = 50
    id: str | None = None  # id no banco (uuid); None nos dados de seed
    order: int = 0

    @property
    def image_path(self) -> str | None:
        if not self.image:
            return None
        path = (IMAGES_DIR / self.image).resolve()
        # evita caminhos fora da pasta de imagens vindos do banco
        if IMAGES_DIR.resolve() not in path.parents or not path.exists():
            return None
        return str(path)

    @property
    def price_label(self) -> str:
        if self.price_type == PRICE_ON_REQUEST or self.price is None:
            return "Preço sob consulta"
        value = format_brl(self.price)
        if self.price_type == PRICE_ESTIMATED:
            return f"Cerca de {value} / {self.unit} (estimado)"
        return f"A partir de {value} / {self.unit}"


def format_brl(value: float) -> str:
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


SEED_PRODUCTS: tuple[Product, ...] = (
    Product("bolo-festa", "Bolo de festa decorado", "Bolos",
            "Massa fofinha, recheio à escolha e decoração personalizada com o tema da sua festa.",
            "kg", 120.0, PRICE_FROM, True, "bolo-festa.svg", 2, 15, order=1),
    Product("naked-cake", "Naked cake com frutas", "Bolos",
            "Camadas aparentes, recheio cremoso e frutas da estação. Ótimo para chás e casamentos.",
            "kg", 140.0, PRICE_FROM, False, "naked-cake.svg", 2, 10, order=2),
    Product("cupcakes", "Cupcakes decorados", "Cupcakes",
            "Cupcakes com cobertura de buttercream e coraçãozinho, na caixa de presente.",
            "caixa com 6", 48.0, PRICE_FROM, True, "cupcakes.svg", 1, 30, order=3),
    Product("brigadeiros", "Brigadeiros gourmet", "Doces",
            "Brigadeiros tradicionais e de sabores especiais, em forminhas para festa.",
            "cento", 150.0, PRICE_ESTIMATED, True, "brigadeiros.svg", 1, 20, order=4),
    Product("bolo-pote", "Bolo de pote", "Doces",
            "Camadas de bolo e recheio no pote, para lembrancinhas ou para adoçar o dia.",
            "unidade", 14.0, PRICE_FROM, True, "bolo-pote.svg", 1, 200, order=5),
    Product("kit-festa", "Kit festa na caixa", "Kits",
            "Bolo, docinhos e cupcakes combinando, montados na caixa para festas pequenas.",
            "kit", None, PRICE_ON_REQUEST, True, "kit-festa.svg", 1, 10, order=6),
)


PRICE_TYPE_LABELS = {
    PRICE_FROM: "A partir de",
    PRICE_ESTIMATED: "Estimado",
    PRICE_ON_REQUEST: "Sob consulta",
}


def available_images() -> list[str]:
    """Imagens que podem ser associadas a produtos (pasta assets/images/produtos)."""
    if not IMAGES_DIR.exists():
        return []
    return sorted(p.name for p in IMAGES_DIR.iterdir() if p.suffix.lower() in {".svg", ".png", ".jpg", ".jpeg", ".webp"})


def slugify(text: str) -> str:
    import unicodedata

    ascii_text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:60]


def validate_product(form: dict, existing_slugs: set[str] | None = None, editing: bool = False) -> tuple[dict, dict]:
    """Valida o cadastro/edição de produto. Retorna (dados limpos, erros por campo).

    Espelha os CHECKs do banco: o banco valida de novo.
    """
    errors: dict[str, str] = {}
    name = " ".join(str(form.get("name") or "").split())
    category = " ".join(str(form.get("category") or "").split())
    description = str(form.get("description") or "").strip()
    unit = " ".join(str(form.get("unit") or "").split())
    price_type = form.get("price_type")
    price = form.get("price")
    image = form.get("image") or None

    if not 2 <= len(name) <= 120:
        errors["name"] = "Nome deve ter entre 2 e 120 caracteres."
    if not 2 <= len(category) <= 60:
        errors["category"] = "Categoria deve ter entre 2 e 60 caracteres."
    if len(description) > 500:
        errors["description"] = "Descrição deve ter no máximo 500 caracteres."
    if not 1 <= len(unit) <= 40:
        errors["unit"] = "Informe a unidade (ex.: kg, unidade, caixa com 6)."
    if price_type not in PRICE_TYPES:
        errors["price_type"] = "Escolha o tipo de preço."
    if price_type == PRICE_ON_REQUEST:
        price = None
    else:
        try:
            price = round(float(price), 2)
            if price < 0:
                raise ValueError
        except (TypeError, ValueError):
            errors["price"] = "Informe um preço válido (zero ou maior)."
            price = None
    try:
        min_qty, max_qty = int(form.get("min_qty")), int(form.get("max_qty"))
        if min_qty < 1 or max_qty < min_qty:
            raise ValueError
    except (TypeError, ValueError):
        errors["qty"] = "Quantidade mínima deve ser 1 ou mais e a máxima não pode ser menor que a mínima."
        min_qty = max_qty = None
    try:
        order = int(form.get("order") or 0)
    except (TypeError, ValueError):
        order = 0
    if image is not None and image not in available_images():
        errors["image"] = "Imagem não encontrada na pasta de produtos."

    data = {
        "name": name, "category": category, "description": description, "unit": unit, "price": price,
        "price_type": price_type, "available": bool(form.get("available")), "image": image,
        "min_qty": min_qty, "max_qty": max_qty, "order": order,
    }
    if not editing:
        slug = slugify(name)
        if len(slug) < 2:
            errors.setdefault("name", "Nome precisa ter letras ou números.")
        elif existing_slugs and slug in existing_slugs:
            errors["name"] = "Já existe um produto com esse nome."
        data["slug"] = slug
    return data, errors


def list_categories(products: list[Product]) -> list[str]:
    return sorted({p.category for p in products})


def find_product(products: list[Product], slug: str) -> Product | None:
    return next((p for p in products if p.slug == slug), None)
