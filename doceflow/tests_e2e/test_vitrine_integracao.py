"""Integração app ↔ página pública: a VITRINE (código publicado, services/repository.py) contra o
mesmo Supabase local em que o app Android (doceflow_app/test_e2e/integracao_vitrine_test.dart) grava.

Ordem: app1 → site1 (este) → app2 → site2 (este). Variáveis E2E_* e E2E_STAMP iguais nas duas pontas.
"""

import os
from dataclasses import replace
from datetime import date, timedelta

import pytest

E = {k: os.environ.get(k, "") for k in ("E2E_SUPABASE_URL", "E2E_PUBLISHABLE_KEY", "E2E_OWNER_EMAIL", "E2E_OWNER_PASS",
                                         "E2E_PHASE", "E2E_STAMP")}
pytestmark = pytest.mark.skipif(not all(E.values()), reason="integração não configurada (variáveis E2E_*)")
if "dfimrkfcudidosdldsjv" in E["E2E_SUPABASE_URL"]:
    raise RuntimeError("Nunca contra produção.")

httpx = pytest.importorskip("httpx")
from config import load_settings  # noqa: E402
from services.order_service import OrderItemRequest, OrderRequest  # noqa: E402
from services.quote_service import LeadRequest, LeadValidationError  # noqa: E402
from services.repository import SupabaseRepository  # noqa: E402
from services.supabase_client import get_supabase_client  # noqa: E402

STAMP = E["E2E_STAMP"]


@pytest.fixture(scope="module")
def site():
    s = replace(load_settings(), db_backend="supabase", supabase_url=E["E2E_SUPABASE_URL"],
                supabase_key=E["E2E_PUBLISHABLE_KEY"], store_slug="kika-cakes")
    return SupabaseRepository(get_supabase_client(s), "kika-cakes"), s


def find(products, name):
    return next((p for p in products if p.name == name), None)


@pytest.mark.skipif(E["E2E_PHASE"] != "site1", reason="fase site1")
def test_site1_storefront_shows_app_product_with_photo_and_takes_orders(site):
    repo, _ = site
    products = repo.list_products()
    p = find(products, f"Integração {STAMP}")
    assert p is not None, "produto publicado pelo app não apareceu na vitrine"
    assert (p.price, p.unit, p.min_qty, p.max_qty, p.featured, p.production_days) == (42.5, "unidade", 1, 10, True, 3)
    assert p.price_label == "A partir de R$ 42,50 / unidade"
    assert p.photo and p.photo.startswith(E["E2E_SUPABASE_URL"]) and "/object/public/product-images/" in p.photo
    img = httpx.get(p.photo, timeout=20)
    assert img.status_code == 200 and img.content[:3] == b"\xff\xd8\xff"  # foto enviada pelo app, servida ao público
    assert find(products, f"Oculto {STAMP}") is None  # despublicado não aparece

    lead = repo.create_lead(LeadRequest(customer_name=f"Cliente Site {STAMP}", whatsapp="5511981230001",
                                        product_slug=p.slug, quantity=2, desired_date=date.today() + timedelta(days=9),
                                        fulfillment="Retirada", notes="integração", consent=True, origin="e2e"))
    assert lead.created and lead.product_name == f"Integração {STAMP}"
    order = repo.create_order(OrderRequest(customer_name=f"Pedido Site {STAMP}", whatsapp="5511981230002",
                                           delivery_date=date.today() + timedelta(days=10), fulfillment="Retirada",
                                           notes="", items=(OrderItemRequest(p.slug, 3),), consent=True, origin="e2e"))
    assert order.created and order.estimated_total == 127.5
    with open(os.path.join(os.path.dirname(__file__), f".slug_{STAMP}"), "w") as fh:  # para a fase site2
        fh.write(p.slug)


@pytest.mark.skipif(E["E2E_PHASE"] != "site2", reason="fase site2")
def test_site2_unpublished_in_app_leaves_storefront_and_panel_sees_app_changes(site):
    repo, settings = site
    assert find(repo.list_products(), f"Integração {STAMP}") is None  # despublicado no app → some da vitrine
    with open(os.path.join(os.path.dirname(__file__), f".slug_{STAMP}")) as fh:
        slug = fh.read()
    with pytest.raises(LeadValidationError):
        repo.create_order(OrderRequest(customer_name="Depois de Ocultar", whatsapp="5511981230003",
                                       delivery_date=date.today() + timedelta(days=10), fulfillment="Retirada", notes="",
                                       items=(OrderItemRequest(slug, 1),), consent=True, origin="e2e"))
    # painel web (mesmo código do admin_app.py) enxerga o que a dona fez no app
    client = get_supabase_client(settings)
    user = client.auth.sign_in_with_password({"email": E["E2E_OWNER_EMAIL"], "password": E["E2E_OWNER_PASS"]}).user
    panel = SupabaseRepository.for_owner(client, user.id, "kika-cakes")
    orders = panel.list_orders()
    site_order = next(o for o in orders if o["cliente_nome"] == f"Pedido Site {STAMP}")
    assert (site_order["status"], float(site_order["valor_final"])) == ("Confirmado", 130.0)
    converted = next(o for o in orders if o["cliente_nome"] == f"Cliente Site {STAMP}")
    assert converted["status"] == "Confirmado" and converted["lead_id"] and float(converted["valor_final"]) == 90.0
    lead = next(l for l in panel.list_leads() if l["cliente_nome"] == f"Cliente Site {STAMP}")
    assert lead["status"] == "Venda concluída"
    os.remove(os.path.join(os.path.dirname(__file__), f".slug_{STAMP}"))
