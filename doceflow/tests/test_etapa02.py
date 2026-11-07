from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from services.catalog import get_product, list_categories, list_products
from services.quotes import (
    DuplicateQuoteError,
    InMemoryQuoteStore,
    normalize_br_whatsapp,
    validate_quote,
)

APP = str(Path(__file__).resolve().parents[1] / "app.py")
TODAY = date(2026, 11, 7)


def valid_form(**overrides):
    form = {
        "customer_name": "Maria Silva",
        "whatsapp": "(11) 98765-4321",
        "product_id": "cupcakes",
        "quantity": 2,
        "desired_date": TODAY + timedelta(days=5),
        "fulfillment": "Retirada",
        "notes": "Tema unicórnio",
        "consent": True,
    }
    form.update(overrides)
    return form


@pytest.fixture(autouse=True)
def clean_env(tmp_path, monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "WHATSAPP_NUMBER", "ADMIN_PASSWORD", "STORE_NAME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "t.db"))


# ---------- Produtos ----------
def test_catalog_has_available_and_unavailable_products():
    products = list_products()
    assert any(p.available for p in products)
    assert any(not p.available for p in products)
    assert {"Bolos", "Cupcakes", "Doces", "Kits"} <= set(list_categories())


def test_every_product_has_existing_image():
    for p in list_products():
        assert Path(p.image_path).exists(), p.id


def test_price_labels_never_look_final():
    for p in list_products():
        label = p.price_label.lower()
        assert any(word in label for word in ("a partir de", "estimado", "sob consulta")), p.id


def test_valid_form_creates_quote_with_all_fields():
    quote, errors = validate_quote(valid_form(), today=TODAY)
    assert errors == {}
    record = quote.to_record()
    for key in ("customer_name", "whatsapp", "product_id", "product_name", "quantity", "unit",
                "desired_date", "fulfillment", "notes", "consent", "status", "protocol", "fingerprint"):
        assert key in record
    assert record["whatsapp"] == "5511987654321"
    assert record["status"] == "novo"


def test_unavailable_product_is_rejected():
    _, errors = validate_quote(valid_form(product_id="naked-cake", quantity=2), today=TODAY)
    assert "indisponível" in errors["product_id"]


def test_unknown_product_is_rejected():
    _, errors = validate_quote(valid_form(product_id="nao-existe"), today=TODAY)
    assert "product_id" in errors


# ---------- Campos vazios ----------
def test_empty_form_reports_every_required_field():
    _, errors = validate_quote({}, today=TODAY)
    assert set(errors) == {"customer_name", "whatsapp", "product_id", "quantity", "desired_date",
                           "fulfillment", "consent"}


def test_blank_name_is_rejected():
    _, errors = validate_quote(valid_form(customer_name="   "), today=TODAY)
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
    "98765-4321",          # sem DDD
    "(11) 8765-432",       # curto
    "(01) 98765-4321",     # DDD inválido
    "(11) 88765-4321",     # celular sem 9 inicial
    "(11) 99999-99999",    # longo
    "(11) 99999-9999 9",   # longo
    "(11) 9999-9999",      # fixo começando com 9
    "11111111111",         # repetido
    "abc",
])
def test_invalid_phones(raw):
    assert normalize_br_whatsapp(raw) is None
    _, errors = validate_quote(valid_form(whatsapp=raw), today=TODAY)
    assert "whatsapp" in errors


# ---------- Datas ----------
def test_past_date_is_rejected():
    _, errors = validate_quote(valid_form(desired_date=TODAY - timedelta(days=1)), today=TODAY)
    assert errors["desired_date"] == "A data não pode estar no passado."


def test_today_is_accepted():
    _, errors = validate_quote(valid_form(desired_date=TODAY), today=TODAY)
    assert "desired_date" not in errors


def test_date_too_far_is_rejected():
    _, errors = validate_quote(valid_form(desired_date=TODAY + timedelta(days=400)), today=TODAY)
    assert "desired_date" in errors


def test_missing_date_is_rejected():
    _, errors = validate_quote(valid_form(desired_date=None), today=TODAY)
    assert errors["desired_date"] == "Informe a data desejada."


# ---------- Quantidade e observações ----------
def test_quantity_out_of_product_range():
    bolo = get_product("bolo-festa")
    _, errors = validate_quote(valid_form(product_id="bolo-festa", quantity=bolo.min_qty - 1), today=TODAY)
    assert "quantity" in errors


def test_notes_too_long():
    _, errors = validate_quote(valid_form(notes="x" * 501), today=TODAY)
    assert "notes" in errors


def test_consent_required():
    _, errors = validate_quote(valid_form(consent=False), today=TODAY)
    assert "consent" in errors


# ---------- Duplicidade ----------
def test_duplicate_submission_is_blocked():
    store = InMemoryQuoteStore()
    first, _ = validate_quote(valid_form(), today=TODAY)
    second, _ = validate_quote(valid_form(whatsapp="+55 11 98765-4321"), today=TODAY)  # mesmo número, outro formato
    store.add(first)
    with pytest.raises(DuplicateQuoteError) as exc:
        store.add(second)
    assert exc.value.existing.protocol == first.protocol
    assert len(store.all()) == 1


def test_different_date_is_not_duplicate():
    store = InMemoryQuoteStore()
    store.add(validate_quote(valid_form(), today=TODAY)[0])
    store.add(validate_quote(valid_form(desired_date=TODAY + timedelta(days=9)), today=TODAY)[0])
    assert len(store.all()) == 2


# ---------- Interface (Streamlit AppTest) ----------
def test_catalog_renders_all_products():
    at = AppTest.from_file(APP).run(timeout=30)
    assert not at.exception
    labels = [b.label for b in at.button]
    assert labels.count("Solicitar orçamento") == sum(p.available for p in list_products())
    assert "Indisponível no momento" in labels


def test_category_filter():
    at = AppTest.from_file(APP).run(timeout=30)
    at.button_group(key="category").set_value("Bolos").run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert labels.count("Solicitar orçamento") == 1  # bolo de festa (naked cake indisponível)


def _open_form(at, product_id="cupcakes"):
    at.button(key=f"req_{product_id}").click().run()
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
    assert at.selectbox(key="f_product").value == "cupcakes"


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


def test_submit_valid_form_shows_confirmation_and_blocks_duplicate():
    at = _open_form(AppTest.from_file(APP).run(timeout=30))
    at = _submit(_fill(at))
    assert any("Solicitação enviada!" in s.value for s in at.success)
    store = at.session_state["quote_store"]
    assert len(store.all()) == 1

    # mesma solicitação de novo
    at = _submit(_fill(_open_form(at)))
    assert any("já enviou esta mesma solicitação" in w.value for w in at.warning)
    assert len(at.session_state["quote_store"].all()) == 1
