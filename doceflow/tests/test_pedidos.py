"""Etapa 4: pedidos (formulário público, protocolo, gestão no painel, histórico e indicadores).

Telas testadas com o AppTest no SQLite local (que espelha a função criar_pedido); a integração
com o Supabase é testada com um cliente falso. As regras do banco estão em test_pedidos_postgres.
"""

from datetime import date, timedelta

import pytest

import config
from services.order_service import (
    ORDER_STATUSES,
    STATUS_CANCELLED,
    STATUS_WAITING,
    OrderItemRequest,
    OrderRequest,
    compute_order_metrics,
    filter_orders,
    history_text,
    summarize,
    validate_order,
)
from services.product_service import SEED_PRODUCTS
from services.quote_service import LeadValidationError
from services.repository import SupabaseRepository, get_repository
from tests.conftest import DASHBOARD, admin_login, open_page

ORDER_PAGE = "pages/public/order.py"
ORDERS_ADMIN = "pages/admin/orders.py"
CATALOG = "pages/public/catalog.py"
PASSWORD = "senha-pedidos-teste"
PRODS = list(SEED_PRODUCTS)
TODAY = date.today()


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "STORE_NAME", "STORE_SLUG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "pedidos.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setenv("WHATSAPP_NUMBER", "5511979855065")


def repo():
    return get_repository(config.load_settings())


def request(phone="5511987650000", fulfillment="Entrega", items=(("bem-casado", 50), ("docinhos-tradicionais", 2)),
            address="Rua das Flores, 123, Centro, São Paulo", days=10):
    return OrderRequest("Maria Pedido", phone, TODAY + timedelta(days=days), fulfillment, "Sem lactose",
                        tuple(OrderItemRequest(s, q) for s, q in items), True,
                        address=address if fulfillment == "Entrega" else "")


def form(**o):
    f = dict(customer_name="Maria Pedido", whatsapp="(11) 98765-4321", delivery_date=TODAY + timedelta(days=9),
             fulfillment="Entrega", address="Rua das Flores, 123, Centro, São Paulo", notes="", consent=True,
             items=[{"product_id": "bem-casado", "quantity": 50}])
    f.update(o)
    return f


# ================================================================ validação e resumo
def test_address_required_only_for_delivery():
    assert "address" in validate_order(form(address="Rua"), PRODS, TODAY)[1]
    req, errors = validate_order(form(fulfillment="Retirada", address="Rua X, 1, Bairro"), PRODS, TODAY)
    assert errors == {} and req.address == ""  # retirada não guarda endereço


def test_summary_before_confirmation():
    s = summarize(request(), PRODS)
    assert [(line.name, line.subtotal) for line in s.lines] == [("Bem Casado", 300.0),
                                                                ("Docinhos Tradicionais", 300.0)]
    assert s.total == 600.0 and s.total_label == "A partir de R$ 600,00"


def test_summary_with_on_request_item_has_no_total():
    from dataclasses import replace

    prods = [replace(p, price_type="sob_consulta", price=None) if p.slug == "bem-casado" else p for p in PRODS]
    s = summarize(request(), prods)
    assert s.total is None and s.has_on_request and "A combinar" in s.total_label


# ================================================================ persistência local (espelha criar_pedido)
def test_order_is_saved_with_prices_from_database():
    order = repo().create_order(request())
    assert order.created and order.protocol.startswith("PD-") and order.status == STATUS_WAITING
    assert order.estimated_total == 600.0
    [saved] = repo().list_orders()
    assert saved["protocolo"] == order.protocol and saved["endereco_entrega"].startswith("Rua das Flores")
    assert {(i["produto_nome"], i["preco_unitario"], i["subtotal"]) for i in saved["itens"]} == {
        ("Bem Casado", 6.0, 300.0), ("Docinhos Tradicionais", 150.0, 300.0)}


def test_items_keep_snapshot_after_product_changes():
    repo().create_order(request())
    pid = next(p.id for p in repo().list_products() if p.slug == "bem-casado")
    repo().update_product(pid, {"name": "Bem-casado Premium", "price": 9.0})
    item = next(i for i in repo().list_orders()[0]["itens"] if i["produto_nome"].startswith("Bem"))
    assert (item["produto_nome"], item["preco_unitario"]) == ("Bem Casado", 6.0)


def test_repeated_order_is_not_duplicated():
    first = repo().create_order(request())
    again = repo().create_order(request())
    assert again.protocol == first.protocol and not again.created and len(repo().list_orders()) == 1


@pytest.mark.parametrize("req,message", [
    (request(items=(("nao-existe", 1),)), "Produto não encontrado"),
    (request(items=(("bem-casado", 10),)), "Quantidade fora"),
    (request(address=""), "endereço"),
    (request(days=-1), "Data inválida"),
])
def test_server_side_validation(req, message):
    with pytest.raises(LeadValidationError, match=message):
        repo().create_order(req)
    assert repo().list_orders() == []


def test_unpublished_or_unavailable_product_cannot_be_ordered():
    pid = next(p.id for p in repo().list_products() if p.slug == "bem-casado")
    repo().update_product(pid, {"published": False})
    with pytest.raises(LeadValidationError):
        repo().create_order(request())
    repo().update_product(pid, {"published": True, "available": False})
    with pytest.raises(LeadValidationError, match="indisponível"):
        repo().create_order(request())


def test_update_records_history():
    order = repo().create_order(request())
    repo().update_order(order.id, {"status": "Confirmado", "valor_final": 650.0})
    history = repo().order_history(order.id)
    assert [h["campo"] for h in history] == ["criado", "status", "valor_final"]
    assert history_text(history[1]) == "Status: Aguardando confirmação → Confirmado"
    assert history_text(history[2]) == "Valor final: — → R$ 650,00"


@pytest.mark.parametrize("fields", [{"status": "Pago"}, {"valor_estimado": 1}, {"cliente_whatsapp": "1"},
                                    {"valor_final": -5}])
def test_update_rejects_invalid_or_forbidden_fields(fields):
    order = repo().create_order(request())
    with pytest.raises(LeadValidationError):
        repo().update_order(order.id, fields)


def test_product_in_an_order_cannot_be_deleted():
    repo().create_order(request(fulfillment="Retirada", items=(("docinhos-tradicionais", 2),)))
    pid = next(p.id for p in repo().list_products() if p.slug == "docinhos-tradicionais")
    with pytest.raises(LeadValidationError, match="Despublique"):
        repo().delete_product(pid)


# ================================================================ filtros e indicadores
def _orders():
    return [
        {"protocolo": "PD-1", "cliente_nome": "Maria Souza", "status": STATUS_WAITING, "valor_estimado": 100,
         "created_at": "2026-11-10T15:00:00+00:00", "data_entrega": "2026-11-20"},
        {"protocolo": "PD-2", "cliente_nome": "João Lima", "status": "Confirmado", "valor_estimado": 250.5,
         "created_at": "2026-11-12T15:00:00+00:00", "data_entrega": "2026-12-01"},
        {"protocolo": "PD-3", "cliente_nome": "Ana Dias", "status": STATUS_CANCELLED, "valor_estimado": 999,
         "created_at": "2026-11-13T15:00:00+00:00", "data_entrega": "2026-11-25"},
        {"protocolo": "PD-4", "cliente_nome": "Bia Reis", "status": "Entregue", "valor_estimado": None,
         "created_at": "2026-11-14T15:00:00+00:00", "data_entrega": "2026-11-15"},
    ]


def test_filters_by_name_protocol_status_and_dates():
    o = _orders()
    assert [x["protocolo"] for x in filter_orders(o, "maria")] == ["PD-1"]
    assert [x["protocolo"] for x in filter_orders(o, "pd-2")] == ["PD-2"]
    assert [x["protocolo"] for x in filter_orders(o, statuses=["Entregue", STATUS_CANCELLED])] == ["PD-3", "PD-4"]
    assert [x["protocolo"] for x in filter_orders(o, start=date(2026, 11, 12), end=date(2026, 11, 13))] == \
        ["PD-2", "PD-3"]
    assert [x["protocolo"] for x in filter_orders(o, start=date(2026, 11, 21), by="desired")] == ["PD-2", "PD-3"]


def test_metrics_separate_registered_value_from_revenue():
    m = compute_order_metrics(_orders())
    assert (m.total, m.waiting, m.confirmed, m.in_production, m.delivered) == (4, 1, 1, 0, 1)
    assert m.registered_value == 350.5  # sem o cancelado e sem o pedido sob consulta
    assert m.without_estimate == 1


# ================================================================ telas
def _fill_public_form(at, items=(("bem-casado", 50),), fulfillment="Entrega",
                      address="Rua das Flores, 123, Centro, São Paulo"):
    at.multiselect(key="ord_0_products").set_value([s for s, _ in items]).run()
    for slug, qty in items:
        at.number_input(key=f"ord_0_qty_{slug}").set_value(qty)
    at.text_input(key="ord_0_name").input("Maria Pedido")
    at.text_input(key="ord_0_phone").input("(11) 98765-4321")
    at.date_input(key="ord_0_date").set_value(TODAY + timedelta(days=8))
    at.radio(key="ord_0_fulfillment").set_value(fulfillment).run()
    if fulfillment == "Entrega":
        at.text_area(key="ord_0_address").input(address)
    at.checkbox(key="ord_0_consent").check()
    return at


def test_catalog_links_to_order_page():
    vitrine = open_page(CATALOG)
    assert any("Já sabe o que quer" in m.value for m in vitrine.markdown)


def test_public_order_flow_summary_then_protocol():
    at = _fill_public_form(open_page(ORDER_PAGE), items=(("bem-casado", 50), ("docinhos-tradicionais", 2)))
    at.button(key="ord_review").click().run()
    assert not at.exception and not at.error
    assert any("A partir de R$ 600,00" in m.value for m in at.markdown)  # resumo antes de confirmar
    assert repo().list_orders() == []  # nada gravado antes da confirmação
    at.button(key="ord_confirm").click().run()
    [saved] = repo().list_orders()
    success = " ".join(s.value for s in at.success)
    assert saved["protocolo"] in success  # protocolo só aparece depois de gravado
    assert any("ainda não confirma" in m.value for m in at.markdown)
    assert at.multiselect(key="ord_1_products").value == []  # formulário limpo para outro pedido


def test_public_order_form_errors_and_back_to_edit():
    at = open_page(ORDER_PAGE)
    at.button(key="ord_review").click().run()
    assert at.error and repo().list_orders() == []
    at = _fill_public_form(open_page(ORDER_PAGE), address="Rua")
    at.button(key="ord_review").click().run()
    assert any("endereço completo" in e.value for e in at.error)
    at.text_area(key="ord_0_address").input("Rua das Flores, 123, Centro, São Paulo")
    at.button(key="ord_review").click().run()
    at.button(key="ord_back").click().run()
    assert at.text_input(key="ord_0_name").value == "Maria Pedido"  # voltar não apaga o que foi digitado
    assert repo().list_orders() == []


def test_visitor_cannot_open_orders_admin():
    repo().create_order(request())
    at = open_page(ORDERS_ADMIN)
    assert at.title[0].value == "Painel administrativo"
    assert not any("PD-" in str(getattr(e, "value", "")) for e in at.markdown)


def test_owner_lists_searches_and_updates_order_with_history():
    first = repo().create_order(request())
    repo().create_order(request(phone="5511912345678", fulfillment="Retirada", items=(("docinhos-tradicionais", 3),)))
    at = admin_login(PASSWORD, ORDERS_ADMIN)
    assert at.title[0].value == "Pedidos" and not at.exception
    assert any("**2** pedido(s) aguardando" in i.value for i in at.info)
    at.text_input(key="ord_q").input(first.protocol).run()
    assert at.selectbox(key="sel_order").options == [f"{first.protocol} · Maria Pedido · {STATUS_WAITING}"]
    at.selectbox(key=f"upd_status_{first.id}").set_value("Confirmado")
    at.number_input(key=f"upd_final_{first.id}").set_value(650.0)
    next(b for b in at.button if b.label == "Salvar alterações").click().run()
    assert not at.exception
    saved = next(o for o in repo().list_orders() if o["id"] == first.id)
    assert saved["status"] == "Confirmado" and saved["valor_final"] == 650.0
    assert any("Status: Aguardando confirmação → Confirmado" in m.value for m in at.markdown)


def test_owner_filters_orders_by_status():
    repo().create_order(request())
    at = admin_login(PASSWORD, ORDERS_ADMIN)
    at.multiselect(key="ord_status").set_value(["Entregue"]).run()
    assert any("Nenhum pedido encontrado" in w.value for w in at.warning)


def test_dashboard_shows_order_indicators():
    order = repo().create_order(request())
    repo().create_order(request(phone="5511912345678", fulfillment="Retirada", items=(("docinhos-tradicionais", 3),)))
    repo().update_order(order.id, {"status": "Em produção"})
    at = admin_login(PASSWORD, DASHBOARD)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Total de pedidos"] == "2" and metrics["Aguardando confirmação"] == "1"
    assert metrics["Em produção"] == "1" and metrics["Valor registrado (estimado)"] == "R$ 1.050,00"
    assert any("não a receita recebida" in c.value for c in at.caption)


def test_statuses_match_specification():
    assert ORDER_STATUSES == ("Aguardando confirmação", "Confirmado", "Em produção", "Pronto", "Entregue",
                              "Cancelado")


# ================================================================ Supabase (cliente falso)
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
        return _Res(self.client.data.get(self.name, []))


class _Client:
    def __init__(self, data):
        self.data, self.calls = data, []

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        self.calls.append(("rpc", name, (params,)))
        return _Query(self, f"rpc:{name}")


STORE = {"id": "11111111-1111-1111-1111-111111111111", "slug": "kika-cakes", "nome": "Kika", "whatsapp": None}


def test_supabase_order_sends_only_slugs_quantities_and_address():
    row = {"id": "o1", "protocolo": "PD-261114-AAA111", "criado": True, "status": STATUS_WAITING,
           "valor_estimado": 600, "confeitaria_nome": "Kika", "confeitaria_whatsapp": "5511979855065"}
    client = _Client({"rpc:criar_pedido": [row]})
    order = SupabaseRepository(client, "kika-cakes").create_order(request())
    params = next(c for c in client.calls if c[0] == "rpc")[2][0]
    assert params["p_endereco_entrega"].startswith("Rua das Flores")
    assert params["p_itens"] == [{"produto_slug": "bem-casado", "quantidade": 50},
                                 {"produto_slug": "docinhos-tradicionais", "quantidade": 2}]
    assert not any("preco" in key or "valor" in key for key in params)  # o navegador não envia preço
    assert order.status == STATUS_WAITING


def test_supabase_lists_orders_with_items_and_history_of_own_store():
    client = _Client({"confeitarias": [STORE], "orders": [{"id": "o1", "protocolo": "PD-1"}],
                      "order_items": [{"order_id": "o1", "produto_nome": "Bolo", "subtotal": 80}],
                      "order_history": [{"campo": "criado"}]})
    r = SupabaseRepository(client, "kika-cakes")
    [o] = r.list_orders()
    assert o["itens"][0]["produto_nome"] == "Bolo"
    assert r.order_history("o1") == [{"campo": "criado"}]
    hist_filters = [c for c in client.calls if c[0] == "order_history" and c[1] == "eq"]
    assert ("order_history", "eq", ("confeitaria_id", STORE["id"])) in hist_filters
