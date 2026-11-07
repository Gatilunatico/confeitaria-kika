"""Catálogo de produtos da vitrine.

Nesta etapa os produtos ficam em memória (dados de EXEMPLO da Kika Cakes).
Na próxima etapa a função `list_products` passa a ler a tabela `produtos`
no Supabase, mantendo a mesma estrutura de `Product`.

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


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    category: str
    description: str
    unit: str  # unidade da quantidade: "kg", "caixa com 6", "unidade"...
    price: float | None
    price_type: str
    available: bool
    image: str
    min_qty: int = 1
    max_qty: int = 50

    @property
    def image_path(self) -> str:
        return str(IMAGES_DIR / self.image)

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


_SAMPLE_PRODUCTS: tuple[Product, ...] = (
    Product(
        id="bolo-festa",
        name="Bolo de festa decorado",
        category="Bolos",
        description="Massa fofinha, recheio à escolha e decoração personalizada com o tema da sua festa.",
        unit="kg",
        price=120.0,
        price_type=PRICE_FROM,
        available=True,
        image="bolo-festa.svg",
        min_qty=2,
        max_qty=15,
    ),
    Product(
        id="naked-cake",
        name="Naked cake com frutas",
        category="Bolos",
        description="Camadas aparentes, recheio cremoso e frutas da estação. Ótimo para chás e casamentos.",
        unit="kg",
        price=140.0,
        price_type=PRICE_FROM,
        available=False,
        image="naked-cake.svg",
        min_qty=2,
        max_qty=10,
    ),
    Product(
        id="cupcakes",
        name="Cupcakes decorados",
        category="Cupcakes",
        description="Cupcakes com cobertura de buttercream e coraçãozinho, na caixa de presente.",
        unit="caixa com 6",
        price=48.0,
        price_type=PRICE_FROM,
        available=True,
        image="cupcakes.svg",
        max_qty=30,
    ),
    Product(
        id="brigadeiros",
        name="Brigadeiros gourmet",
        category="Doces",
        description="Brigadeiros tradicionais e de sabores especiais, em forminhas para festa.",
        unit="cento",
        price=150.0,
        price_type=PRICE_ESTIMATED,
        available=True,
        image="brigadeiros.svg",
        max_qty=20,
    ),
    Product(
        id="bolo-pote",
        name="Bolo de pote",
        category="Doces",
        description="Camadas de bolo e recheio no pote, para lembrancinhas ou para adoçar o dia.",
        unit="unidade",
        price=14.0,
        price_type=PRICE_FROM,
        available=True,
        image="bolo-pote.svg",
        max_qty=200,
    ),
    Product(
        id="kit-festa",
        name="Kit festa na caixa",
        category="Kits",
        description="Bolo, docinhos e cupcakes combinando, montados na caixa para festas pequenas.",
        unit="kit",
        price=None,
        price_type=PRICE_ON_REQUEST,
        available=True,
        image="kit-festa.svg",
        max_qty=10,
    ),
)


def list_products() -> list[Product]:
    return list(_SAMPLE_PRODUCTS)


def list_categories(products: list[Product] | None = None) -> list[str]:
    products = products if products is not None else list_products()
    return sorted({p.category for p in products})


def get_product(product_id: str) -> Product | None:
    return next((p for p in list_products() if p.id == product_id), None)
