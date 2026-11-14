"""Etapa 2 (segurança): camada de autorização do app, publicação, pedidos e fotos."""

from datetime import date, timedelta
from io import BytesIO

import pytest
from PIL import Image

import config
from services.catalog_data import CATALOGO  # noqa: F401  (garante dados oficiais carregados)
from services.image_service import ImageError, image_path, upload_product_image, validate_image
from services.order_service import ORDER_STATUSES, validate_order, validate_order_update
from services.product_service import SEED_PRODUCTS, find_product
from services.quote_service import LeadRequest, LeadValidationError
from services.repository import SupabaseRepository, get_repository
from tests.conftest import DASHBOARD, LOGIN, MARKETING_PAGE, PRODUCTS, QUOTES, admin_login, open_app, open_page

PRODS = list(SEED_PRODUCTS)
TODAY = date(2026, 11, 14)


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "STORE_NAME", "STORE_SLUG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "seg.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", "senha-seg-teste")


def repo():
    return get_repository(config.load_settings())


# ================================================================ páginas administrativas
@pytest.mark.parametrize("page", [DASHBOARD, QUOTES, PRODUCTS, MARKETING_PAGE])
def test_visitor_cannot_open_admin_pages(page):
    at = open_page(page)
    assert at.title[0].value == "Painel administrativo"  # caiu no login
    assert not at.metric and not at.get("download_button")
    assert not any(b.label in ("Salvar status", "Salvar produto", "Salvar no histórico") for b in at.button)


def test_visitor_has_no_admin_menu_and_session_flag_alone_is_not_enough():
    at = open_app()
    at.session_state["admin_ok"] = True  # tentativa de forjar a sessão
    at.run()
    at.switch_page(QUOTES).run()
    assert at.title[0].value == "Painel administrativo"


def test_owner_reaches_admin_pages_after_login():
    at = admin_login("senha-seg-teste", PRODUCTS)
    assert at.title[0].value == "Produtos"


# ================================================================ produtos publicados
def test_unpublished_product_hidden_from_storefront_but_visible_to_owner():
    r = repo()
    pid = next(p.id for p in r.list_products() if p.slug == "bem-casado")
    r.update_product(pid, {"published": False})
    vitrine = open_page("pages/public/catalog.py")
    assert "req_bem-casado" not in [b.key for b in vitrine.button]
    assert [b.label for b in vitrine.button].count("Solicitar orçamento") == 26
    assert any(p.slug == "bem-casado" and not p.published for p in repo().list_products())


def test_unpublished_product_cannot_be_quoted_even_bypassing_the_page():
    r = repo()
    pid = next(p.id for p in r.list_products() if p.slug == "bem-casado")
    r.update_product(pid, {"published": False})
    with pytest.raises(LeadValidationError):
        repo().create_lead(LeadRequest("Ana Teste", "5511987650000", "bem-casado", 50,
                                       date.today() + timedelta(days=5), "Retirada", "", True))


def test_owner_toggles_published_in_product_form():
    pid = next(p.id for p in repo().list_products() if p.slug == "cupcake-tag")
    at = admin_login("senha-seg-teste", PRODUCTS)
    at.selectbox(key="sel_product").set_value(pid).run()
    at.checkbox(key=f"edit_{pid}_pub").uncheck()
    next(b for b in at.button if b.label == "Salvar produto").click().run()
    assert not at.exception
    assert not next(p for p in repo().list_products() if p.slug == "cupcake-tag").published


# ================================================================ pedidos (validação do app)
def _order_form(**o):
    f = dict(customer_name="Maria Pedido", whatsapp="(11) 98765-4321", delivery_date=TODAY + timedelta(days=9),
             fulfillment="Entrega", notes="", consent=True, address="Rua das Flores, 123, Centro, São Paulo",
             items=[{"product_id": "bem-casado", "quantity": 50}, {"product_id": "docinhos-tradicionais",
                                                                    "quantity": 2}])
    f.update(o)
    return f


def test_valid_order():
    req, errors = validate_order(_order_form(), PRODS, TODAY)
    assert errors == {} and len(req.items) == 2
    assert req.rpc_items() == [{"produto_slug": "bem-casado", "quantidade": 50},
                               {"produto_slug": "docinhos-tradicionais", "quantidade": 2}]


@pytest.mark.parametrize("override,field", [
    ({"items": []}, "items"),
    ({"items": [{"product_id": "bem-casado", "quantity": 10}]}, "items"),
    ({"items": [{"product_id": "bem-casado", "quantity": 50}] * 2}, "items"),
    ({"items": [{"product_id": "nao-existe", "quantity": 1}]}, "items"),
    ({"items": [{"product_id": "bem-casado", "quantity": 30}] * 21}, "items"),
    ({"whatsapp": "123"}, "whatsapp"),
    ({"delivery_date": TODAY - timedelta(days=1)}, "delivery_date"),
    ({"consent": False}, "consent"),
])
def test_invalid_order(override, field):
    _, errors = validate_order(_order_form(**override), PRODS, TODAY)
    assert field in errors


def test_unpublished_product_rejected_in_order():
    from dataclasses import replace

    prods = [replace(p, published=False) if p.slug == "bem-casado" else p for p in PRODS]
    _, errors = validate_order(_order_form(), prods, TODAY)
    assert "items" in errors


def test_admin_order_update_only_allowed_fields():
    assert validate_order_update({"status": "Confirmado", "valor_final": 420}) == {"status": "Confirmado",
                                                                                  "valor_final": 420}
    for bad in ({"cliente_whatsapp": "5511900000000"}, {"status": "Pago"}, {"valor_final": -1},
                {"confeitaria_id": "x"}):
        with pytest.raises(ValueError):
            validate_order_update(bad)
    assert ORDER_STATUSES[0] == "Aguardando confirmação"


def test_local_backend_starts_without_orders():
    assert repo().list_orders() == []  # pedidos também funcionam no SQLite local (Etapa 4)


# ================================================================ Supabase com cliente falso
class _Res:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, name):
        self.client, self.name = client, name

    def __getattr__(self, attr):
        def call(*args, **kwargs):
            self.client.calls.append((self.name, attr, args))
            return self
        return call

    def execute(self):
        if self.client.fail.get(self.name):
            raise self.client.fail[self.name]
        return _Res(self.client.data.get(self.name, [{"id": "x"}]))


class _Bucket:
    def __init__(self, client):
        self.client = client

    def upload(self, path, data, options):
        self.client.calls.append(("storage", "upload", (path, options)))

    def remove(self, paths):
        self.client.calls.append(("storage", "remove", (paths,)))


class _Client:
    def __init__(self, data=None, fail=None):
        self.data, self.fail, self.calls = data or {}, fail or {}, []
        self.storage = type("S", (), {"from_": lambda _s, bucket: _Bucket(self)})()

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        self.calls.append(("rpc", name, (params,)))
        return _Query(self, f"rpc:{name}")


STORE = "11111111-1111-1111-1111-111111111111"
PRODUCT = "22222222-2222-2222-2222-222222222222"


def test_create_order_uses_rpc_with_configured_store_only():
    req, _ = validate_order(_order_form(), PRODS, date.today())
    rpc_row = {"id": "o1", "protocolo": "PD-261114-ABC123", "criado": True, "status": "Aguardando confirmação",
               "valor_estimado": 600, "confeitaria_nome": "Kika Cakes", "confeitaria_whatsapp": "5511979855065"}
    client = _Client(data={"rpc:criar_pedido": [rpc_row]})
    order = SupabaseRepository(client, "kika-cakes").create_order(req)
    _, name, (params,) = next(c for c in client.calls if c[0] == "rpc")
    assert name == "criar_pedido" and params["p_confeitaria_slug"] == "kika-cakes"
    assert "p_confeitaria_id" not in params  # o visitante nunca escolhe o id da confeitaria
    assert order.protocol == "PD-261114-ABC123" and order.estimated_total == 600


def test_order_rate_limit_message():
    class _ApiError(Exception):
        def __init__(self):
            super().__init__("limite_excedido")
            self.message, self.code = "limite_excedido", "22023"

    req, _ = validate_order(_order_form(), PRODS, date.today())
    client = _Client(fail={"rpc:criar_pedido": _ApiError()})
    with pytest.raises(LeadValidationError, match="muitas solicitações"):
        SupabaseRepository(client, "kika-cakes").create_order(req)


def _png(size=(40, 30)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, "pink").save(buf, format="PNG")
    return buf.getvalue()


def test_image_validation_checks_real_content():
    assert validate_image(_png()) == ("png", "image/png")
    with pytest.raises(ImageError):
        validate_image(b"<script>alert(1)</script>")
    with pytest.raises(ImageError):
        validate_image(b"\x89PNG" + b"0" * (5 * 1024 * 1024 + 1))
    gif = BytesIO()
    Image.new("RGB", (5, 5)).save(gif, format="GIF")
    with pytest.raises(ImageError):
        validate_image(gif.getvalue())


def test_image_path_cannot_escape_store_folder():
    with pytest.raises(ValueError):
        image_path("../outra", PRODUCT, STORE, "png")
    assert image_path(STORE, PRODUCT, STORE, "png") == f"{STORE}/{PRODUCT}/{STORE}.png"


def test_upload_goes_to_store_folder_and_cleans_up_on_failure():
    client = _Client()
    row = upload_product_image(client, STORE, PRODUCT, _png(), "Bem casado", principal=True)
    upload = next(c for c in client.calls if c[1] == "upload")
    assert upload[2][0].startswith(f"{STORE}/{PRODUCT}/") and upload[2][1]["content-type"] == "image/png"
    assert row["principal"] is True

    failing = _Client(fail={"product_images": RuntimeError("RLS")})
    with pytest.raises(ImageError):
        upload_product_image(failing, STORE, PRODUCT, _png())
    assert any(c[1] == "remove" for c in failing.calls)
