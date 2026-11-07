"""Etapa 05 (QA): catálogo oficial e regressões dos defeitos encontrados na revisão."""

from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from streamlit.testing.v1 import AppTest

from services.catalog import SEED_PRODUCTS, find_product, list_categories
from services.catalogo_kika import WHATSAPP_OFICIAL

APP = str(Path(__file__).resolve().parents[1] / "app.py")


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "STORE_NAME", "STORE_SLUG", "ADMIN_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "qa.db"))
    monkeypatch.setenv("WHATSAPP_NUMBER", WHATSAPP_OFICIAL)


# ------------------------------------------------ catálogo oficial (PDFs de nov/2026)
# (slug, preço, unidade, mínimo) conferidos item a item com os cardápios
PDF_PRICES = [
    ("bolo-tradicional", 90.0, "kg", 1), ("bolo-especial", 95.0, "kg", 1),
    ("bolo-nobre-frutas", 100.0, "kg", 1), ("bolo-geleia-artesanal", 110.0, "kg", 1),
    ("docinhos-tradicionais", 150.0, "cento", 1), ("docinhos-premium", 200.0, "cento", 1),
    ("pirulito-ao-leite-tag", 6.0, "unidade", 6), ("pirulito-branco-tag", 7.0, "unidade", 6),
    ("pao-de-mel-palito-tag", 10.0, "unidade", 6), ("maca-de-chocolate-tag", 14.0, "unidade", 6),
    ("cupcake-tag", 8.5, "unidade", 6),
    ("brownie-etiqueta", 8.0, "unidade", 1), ("mini-pao-de-mel-etiqueta", 5.0, "unidade", 1),
    ("pirulito-ao-leite-pasta", 9.5, "unidade", 6), ("pirulito-branco-pasta", 10.5, "unidade", 6),
    ("pao-de-mel-palito-pasta", 14.0, "unidade", 6), ("mini-pao-de-mel-pasta", 6.5, "unidade", 6),
    ("maca-de-chocolate-pasta", 16.0, "unidade", 6), ("cupcake-pasta", 12.0, "unidade", 6),
    ("baby-brownie", 2.5, "unidade", 25), ("bem-casado", 6.0, "unidade", 25),
    ("mini-trufa-simples-blend", 1.6, "unidade", 50), ("mini-trufa-simples-branca", 1.8, "unidade", 50),
    ("mini-trufa-decorada-blend", 2.6, "unidade", 50), ("mini-trufa-decorada-branca", 2.8, "unidade", 50),
    ("copinho-chocolate-blend", 3.8, "unidade", 50), ("copinho-chocolate-branco", 4.5, "unidade", 50),
]


def test_catalog_has_exactly_the_27_official_products():
    assert sorted(p.slug for p in SEED_PRODUCTS) == sorted(s for s, *_ in PDF_PRICES)


@pytest.mark.parametrize("slug,price,unit,min_qty", PDF_PRICES)
def test_price_unit_and_minimum_match_pdf(slug, price, unit, min_qty):
    p = find_product(list(SEED_PRODUCTS), slug)
    assert (p.price, p.unit, p.min_qty, p.available) == (price, unit, min_qty, True)
    assert p.image_path, f"imagem ausente para {slug}"


def test_every_flavor_from_pdfs_is_listed():
    text = " ".join(p.description for p in SEED_PRODUCTS)
    for flavor in ["Dois Amores", "Olho de Sogra", "Sensação", "Brigadeiro de Maracujá", "Frutas Amarelas",
                   "Geleia de Frutas Vermelhas", "Beijinho", "Bicho de Pé", "Ferrero Rocher", "Churros",
                   "Surpresa de Uva", "Ninho com Nutella", "Doce de Leite", "limão", "maracujá"]:
        assert flavor in text, flavor


def test_categories_follow_menu_order():
    assert list_categories(list(SEED_PRODUCTS)) == [
        "Bolos", "Docinhos", "Personalizados com Tag", "Personalizados com Etiqueta",
        "Personalizados em Pasta Americana", "Doces Finos"]


def test_storefront_lists_all_27_products():
    at = AppTest.from_file(APP).run(timeout=30)
    assert not at.exception
    assert [b.label for b in at.button].count("Solicitar orçamento") == 27


# ------------------------------------------------ regressões da revisão de QA
def _submit_valid(at, slug="bem-casado", qty=50):
    at.button(key=f"req_{slug}").click().run()
    at.text_input(key="f_name").input("Paula QA")
    at.text_input(key="f_phone").input("(11) 98765-4321")
    at.number_input(key=f"f_qty_{slug}").set_value(qty)
    at.date_input(key="f_date").set_value(date.today() + timedelta(days=10))
    at.checkbox(key="f_consent").check()
    next(b for b in at.button if b.label == "Enviar solicitação").click().run()
    assert not at.exception
    return at


def test_qa01_confirmation_and_whatsapp_shown_inside_dialog():
    """QA-01: no celular a confirmação no topo ficava fora da tela; agora aparece no diálogo."""
    at = _submit_valid(AppTest.from_file(APP).run(timeout=30))
    assert at.session_state["dialog_confirmed"] is True
    assert any("Solicitação registrada!" in s.value for s in at.success)
    links = list(at.get("link_button"))
    assert len(links) == 1  # só no diálogo, sem duplicar na página
    url = urlparse(links[0].proto.url)
    assert url.netloc == "wa.me" and url.path == f"/{WHATSAPP_OFICIAL}"
    assert "Bem Casado" in parse_qs(url.query)["text"][0]
    assert any(b.label == "Fechar" for b in at.button)


def test_qa01_close_dialog_keeps_confirmation_on_page():
    at = _submit_valid(AppTest.from_file(APP).run(timeout=30))
    at.button(key="close_confirmation").click().run()
    assert "dialog_confirmed" not in at.session_state
    assert any("Solicitação registrada!" in s.value for s in at.success)
    assert any(b.label == "Fazer nova solicitação" for b in at.button)


def test_qa01_choosing_another_product_opens_a_fresh_form():
    at = _submit_valid(AppTest.from_file(APP).run(timeout=30))
    at.button(key="req_baby-brownie").click().run()
    assert at.selectbox(key="f_product").value == "baby-brownie"  # formulário novo, não a confirmação
    assert "dialog_confirmed" not in at.session_state
    assert not any(b.key == "close_confirmation" for b in at.button)


def test_qa02_error_message_does_not_point_to_wrong_place():
    """QA-02: dizia 'Confira os campos abaixo', mas os campos ficam acima da mensagem."""
    at = AppTest.from_file(APP).run(timeout=30)
    at.button(key="req_bem-casado").click().run()
    next(b for b in at.button if b.label == "Enviar solicitação").click().run()
    text = " ".join(e.value for e in at.error)
    assert "Corrija estes campos" in text and "abaixo" not in text


def test_minimum_quantity_from_menu_is_enforced():
    at = _submit_valid(AppTest.from_file(APP).run(timeout=30), qty=10)
    assert any("entre 25 e 1000" in e.value for e in at.error)
    assert "last_lead" not in at.session_state
