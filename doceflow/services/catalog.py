"""Modelo de produto do catálogo e dados iniciais (seed) de exemplo.

Os produtos exibidos na vitrine vêm do banco (tabela `produtos`) pelo
repositório em `database.py`. `SEED_PRODUCTS` só alimenta o SQLite local e
espelha `supabase/seed.sql`.

Preços são sempre INICIAIS ou ESTIMADOS: o valor final depende de tamanho,
recheio e personalização e é confirmado pela confeitaria.
"""

from __future__ import annotations

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


def list_categories(products: list[Product]) -> list[str]:
    return sorted({p.category for p in products})


def find_product(products: list[Product], slug: str) -> Product | None:
    return next((p for p in products if p.slug == slug), None)
