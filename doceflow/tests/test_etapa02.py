"""Etapa 02: vitrine, formulário e validações.

Atualizado na etapa 03: o catálogo vem do banco (seed em SEED_PRODUCTS),
`validate_quote` virou `validate_lead(form, products)` e a deduplicação passou
para o repositório (testada em test_etapa03.py).
"""

from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from services.catalog import SEED_PRODUCTS, find_product, list_categories
from services.leads import normalize_br_whatsapp, validate_lead
from tests.conftest import UNAVAILABLE_SLUG, mark_unavailable
from dataclasses import replace

APP = str(Path(__file__).resolve().parents[1] / "app.py")
TODAY = date(2026, 11, 7)
PRODUCTS = [replace(p, available=False) if p.slug == UNAVAILABLE_SLUG else p for p in SEED_PRODUCTS]


def valid_form(**overrides):
    form = {
        "customer_name": "Maria Silva",
        "whatsapp": "(11) 98765-4321",
        "product_id": "docinhos-tradicionais",
        "quantity": 2,
        "desired_date": TODAY + timedelta(days=5),
        "fulfillment": "Retirada",
        "notes": "Tema unicórnio",
        "consent": True,
    }
    form.update(overrides)
    return form


def check(form, today=TODAY):
    return validate_lead(form, PRODUCTS, today=today)


@pytest.fixture(autouse=True)
def clean_env(tmp_path, monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "WHATSAPP_NUMBER", "ADMIN_PASSWORD", "STORE_NAME", "STORE_SLUG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "t.db"))
    mark_unavailable()


# ---------- Produtos ----------
def test_catalog_has_available_and_unavailable_products():
    assert any(p.available for p in PRODUCTS)
    assert any(not p.available for p in PRODUCTS)
    assert {"Bolos", "Docinhos", "Doces Finos", "Personalizados com Tag"} <= set(list_categories(PRODUCTS))


def test_every_product_has_existing_image():
    for p in PRODUCTS:
        assert p.image_path and Path(p.image_path).exists(), p.slug


def test_image_path_cannot_escape_images_folder():
    from dataclasses import replace

    evil = replace(PRODUCTS[0], image="../../config.py")
    assert evil.image_path is None


def test_price_labels_never_look_final():
    for p in PRODUCTS:
        label = p.price_label.lower()
        assert any(word in label for word in ("a partir de", "estimado", "sob consulta")), p.slug


def test_valid_form_creates_request():
    request, errors = check(valid_form())
    assert errors == {}
    assert request.whatsapp == "5511987654321"
    assert request.product_slug == "docinhos-tradicionais"
    assert request.origin == "site"


def test_unavailable_product_is_rejected():
    _, errors = check(valid_form(product_id=UNAVAILABLE_SLUG, quantity=2))
    assert "indisponível" in errors["product_id"]


def test_unknown_product_is_rejected():
    _, errors = check(valid_form(product_id="nao-existe"))
    assert "product_id" in errors


# ---------- Campos vazios ----------
def test_empty_form_reports_every_required_field():
    _, errors = validate_lead({}, PRODUCTS, today=TODAY)
    assert set(errors) == {"customer_name", "whatsapp", "product_id", "quantity", "desired_date",
                           "fulfillment", "consent"}


def test_blank_name_is_rejected():
    _, errors = check(valid_form(customer_name="   "))
    assert errors["customer_name"] == "Informe seu nome."


# ---------- Telefones ----------
@pytest.mark.parametrize("raw,expected", [
    ("(11) 98765-4321", "5511987654321"),
    ("+55 11 98765-4321", "5511987654321"),
    ("011987654321", "5511987654321"),
    ("(21) 3456-7890", "552134567890"),
])
def test_valid_phones(raw, expected):
    assert normalize_br_whatsapp(raw) == expected


@pytest.mark.parametrize("raw", [
    "98765-4321", "(11) 8765-432", "(01) 98765-4321", "(11) 88765-4321",
    "(11) 99999-99999", "(11) 99999-9999 9", "(11) 9999-9999", "11111111111", "abc",
])
def test_invalid_phones(raw):
    assert normalize_br_whatsapp(raw) is None
    _, errors = check(valid_form(whatsapp=raw))
    assert "whatsapp" in errors


# ---------- Datas ----------
def test_past_date_is_rejected():
    _, errors = check(valid_form(desired_date=TODAY - timedelta(days=1)))
    assert errors["desired_date"] == "A data não pode estar no passado."


def test_today_is_accepted():
    _, errors = check(valid_form(desired_date=TODAY))
    assert "desired_date" not in errors


def test_date_too_far_is_rejected():
    _, errors = check(valid_form(desired_date=TODAY + timedelta(days=400)))
    assert "desired_date" in errors


def test_missing_date_is_rejected():
    _, errors = check(valid_form(desired_date=None))
    assert errors["desired_date"] == "Informe a data desejada."


# ---------- Quantidade e observações ----------
def test_quantity_out_of_product_range():
    bolo = find_product(PRODUCTS, "bolo-tradicional")
    _, errors = check(valid_form(product_id="bolo-tradicional", quantity=bolo.min_qty - 1))
    assert "quantity" in errors


def test_notes_too_long():
    _, errors = check(valid_form(notes="x" * 501))
    assert "notes" in errors


def test_consent_required():
    _, errors = check(valid_form(consent=False))
    assert "consent" in errors


# ---------- Interface (Streamlit AppTest) ----------
def test_catalog_renders_all_products():
    at = AppTest.from_file(APP).run(timeout=30)
    assert not at.exception
    labels = [b.label for b in at.button]
    assert labels.count("Solicitar orçamento") == sum(p.available for p in PRODUCTS)
    assert "Indisponível no momento" in labels


def test_category_filter():
    at = AppTest.from_file(APP).run(timeout=30)
    at.button_group(key="category").set_value("Bolos").run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert labels.count("Solicitar orçamento") == 3  # 4 bolos, 1 marcado como indisponível


def _open_form(at, slug="docinhos-tradicionais"):
    at.button(key=f"req_{slug}").click().run()
    assert not at.exception
    return at


def _fill(at, **values):
    defaults = {"f_name": "Maria Silva", "f_phone": "(11) 98765-4321"}
    defaults.update(values)
    for key, value in defaults.items():
        at.text_input(key=key).input(value)
    at.date_input(key="f_date").set_value(date.today() + timedelta(days=3))
    at.checkbox(key="f_consent").check()
    return at


def _submit(at):
    next(b for b in at.button if b.label == "Enviar solicitação").click().run()
    assert not at.exception
    return at


def test_select_product_opens_form_with_product():
    at = _open_form(AppTest.from_file(APP).run(timeout=30))
    assert at.selectbox(key="f_product").value == "docinhos-tradicionais"


def test_submit_empty_form_shows_errors():
    at = _submit(_open_form(AppTest.from_file(APP).run(timeout=30)))
    text = " ".join(e.value for e in at.error)
    assert "Informe seu nome." in text
    assert "Informe seu WhatsApp com DDD." in text
    assert "Informe a data desejada." in text


def test_submit_invalid_phone_shows_error():
    at = _open_form(AppTest.from_file(APP).run(timeout=30))
    at = _submit(_fill(at, f_phone="1234"))
    assert any("WhatsApp inválido" in e.value for e in at.error)


def test_submit_valid_form_shows_confirmation_and_repeat_does_not_duplicate():
    at = _open_form(AppTest.from_file(APP).run(timeout=30))
    at = _submit(_fill(at))
    assert any("Solicitação registrada!" in s.value for s in at.success)
    first = at.session_state["last_lead"]

    at = _submit(_fill(_open_form(at)))
    assert any("já estava registrado" in i.value for i in at.info)
    assert at.session_state["last_lead"].protocol == first.protocol
