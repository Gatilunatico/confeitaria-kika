"""Utilidades compartilhadas pelos testes.

O catálogo oficial da Kika Cakes (services/catalogo_kika.py) não tem produtos
indisponíveis. Para testar esse caso, os testes marcam UNAVAILABLE_SLUG como
indisponível no banco de teste.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")
LOGIN = "pages/admin/login.py"
DASHBOARD = "pages/admin/dashboard.py"
QUOTES = "pages/admin/quotes.py"
PRODUCTS = "pages/admin/products.py"
MARKETING_PAGE = "pages/admin/marketing.py"
PRIVACY = "pages/public/privacy.py"


def open_app(timeout: int = 60):
    """App completo (app.py com st.navigation), como no navegador."""
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(APP, default_timeout=timeout)


def open_page(page: str):
    at = open_app().run()
    at.switch_page(page).run()
    return at


def admin_login(password: str, page: str | None = None, email: str | None = None):
    """Entra pela página de login (como a proprietária) e, se pedido, abre outra página."""
    at = open_page(LOGIN)
    if email is None:
        at.text_input[0].input(password)
    else:
        at.text_input[0].input(email)
        at.text_input[1].input(password)
    at.button[0].click().run()
    if page:
        at.switch_page(page).run()
    return at

DEFAULT_SLUG = "docinhos-tradicionais"  # unidade "cento", quantidade de 1 a 20
UNAVAILABLE_SLUG = "bolo-geleia-artesanal"


def _pyarrow_ok() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except Exception:
        return False


PYARROW_OK = _pyarrow_ok()


def pytest_collection_modifyitems(config, items):
    """Testes que leem at.dataframe dependem do pyarrow. Nesta máquina ele pode estar
    bloqueado pela política de Controle de Aplicativo do Windows; nesse caso são
    pulados com o motivo explícito (o app usa uma tabela HTML no lugar)."""
    if PYARROW_OK:
        return
    skip = pytest.mark.skip(reason="pyarrow bloqueado neste Windows (Controle de Aplicativo)")
    for item in items:
        if "dataframe" in getattr(item.function, "__code__", None).co_names if hasattr(item, "function") else False:
            item.add_marker(skip)


def mark_unavailable(slug: str = UNAVAILABLE_SLUG) -> None:
    import config
    from services.repository import get_repository

    repo = get_repository(config.load_settings())
    product = next(p for p in repo.list_products() if p.slug == slug)
    repo.update_product(product.id, {"available": False})
