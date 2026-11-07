"""Utilidades compartilhadas pelos testes.

O catálogo oficial da Kika Cakes (services/catalogo_kika.py) não tem produtos
indisponíveis. Para testar esse caso, os testes marcam UNAVAILABLE_SLUG como
indisponível no banco de teste.
"""

DEFAULT_SLUG = "docinhos-tradicionais"  # unidade "cento", quantidade de 1 a 20
UNAVAILABLE_SLUG = "bolo-geleia-artesanal"


def mark_unavailable(slug: str = UNAVAILABLE_SLUG) -> None:
    import config
    from database import get_repository

    repo = get_repository(config.load_settings())
    product = next(p for p in repo.list_products() if p.slug == slug)
    repo.update_product(product.id, {"available": False})
