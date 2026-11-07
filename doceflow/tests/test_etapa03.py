"""Etapa 03: persistência de leads, WhatsApp, falhas e privacidade (SQLite + app)."""

import logging
import sqlite3
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from streamlit.testing.v1 import AppTest

import config
import database
from database import SQLiteRepository, SupabaseRepository, get_repository
from services.leads import (
    Lead,
    LeadPersistenceError,
    LeadRequest,
    LeadValidationError,
    normalize_origin,
)
from services.whatsapp import build_lead_message, build_wa_link, lead_wa_link

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")
ADMIN = str(ROOT / "pages" / "admin.py")
CUSTOMER_NAME = "Joana Teste"
CUSTOMER_PHONE = "5511987654321"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "ADMIN_PASSWORD", "STORE_NAME", "STORE_SLUG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "doceflow.db"))
    monkeypatch.setenv("WHATSAPP_NUMBER", "5511912345678")
    return tmp_path


def request(**overrides) -> LeadRequest:
    data = dict(
        customer_name=CUSTOMER_NAME, whatsapp=CUSTOMER_PHONE, product_slug="cupcakes", quantity=2,
        desired_date=date.today() + timedelta(days=10), fulfillment="Entrega",
        notes="Tema jardim & flores #rosa", consent=True, origin="instagram",
    )
    data.update(overrides)
    return LeadRequest(**data)


def repo() -> SQLiteRepository:
    return get_repository(config.load_settings())


# ------------------------------------------------------------ banco / modelo
def test_schema_has_three_tables_with_fk_and_timestamps():
    repo()
    with sqlite3.connect(config.load_settings().sqlite_path) as conn:
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
        assert {"confeitarias", "produtos", "leads"} <= tables
        fks = {r[2] for r in conn.execute("pragma foreign_key_list(leads)")}
        assert fks == {"confeitarias", "produtos"}
        cols = {r[1] for r in conn.execute("pragma table_info(leads)")}
        assert {"id", "created_at", "updated_at", "status", "origem", "consentimento_em"} <= cols


def test_valid_lead_is_persisted_with_status_novo_and_origin():
    lead = repo().create_lead(request())
    assert lead.created and lead.status == "Novo"
    assert lead.protocol.startswith("DF-")
    rows = repo().list_leads()
    assert len(rows) == 1
    assert rows[0]["status"] == "Novo"
    assert rows[0]["origem"] == "instagram"
    assert rows[0]["protocolo"] == lead.protocol


def test_lead_survives_restart():
    """Nova instância do repositório (= app reiniciado) lê o lead do arquivo."""
    lead = repo().create_lead(request())
    database_module_reloaded = get_repository(config.load_settings())
    rows = database_module_reloaded.list_leads()
    assert [r["protocolo"] for r in rows] == [lead.protocol]


def test_repeated_action_does_not_duplicate():
    r = repo()
    first = r.create_lead(request())
    again = r.create_lead(request(notes="mudei a observação"))
    assert first.created and not again.created
    assert again.protocol == first.protocol
    assert len(r.list_leads()) == 1


def test_different_order_creates_new_lead():
    r = repo()
    r.create_lead(request())
    r.create_lead(request(quantity=3))
    assert len(r.list_leads()) == 2


@pytest.mark.parametrize("override,message", [
    ({"product_slug": "naked-cake"}, "indisponível"),
    ({"product_slug": "nao-existe"}, "não encontrado"),
    ({"quantity": 999}, "Quantidade"),
    ({"desired_date": date.today() - timedelta(days=1)}, "Data inválida"),
    ({"consent": False}, "concordar"),
])
def test_server_side_validation(override, message):
    with pytest.raises(LeadValidationError, match=message):
        repo().create_lead(request(**override))
    assert repo().list_leads() == []


def test_database_constraint_blocks_bad_phone():
    with pytest.raises(LeadValidationError):
        repo().create_lead(request(whatsapp="123"))


def test_leads_are_scoped_to_configured_store(monkeypatch):
    repo().create_lead(request())
    monkeypatch.setenv("STORE_SLUG", "outra-confeitaria")
    monkeypatch.setenv("STORE_NAME", "Outra")
    other = repo()
    assert other.list_leads() == []
    other.create_lead(request())
    assert len(other.list_leads()) == 1
    monkeypatch.setenv("STORE_SLUG", "kika-cakes")
    assert len(repo().list_leads()) == 1


def test_logs_do_not_contain_personal_data(caplog):
    caplog.set_level(logging.DEBUG)
    r = repo()
    r.create_lead(request())
    with pytest.raises(LeadValidationError):
        r.create_lead(request(whatsapp="123"))
    text = caplog.text
    assert CUSTOMER_NAME not in text and CUSTOMER_PHONE not in text and "123" not in text.replace("DF-", "")


def test_sql_injection_is_stored_as_text():
    payload = "Robert'); DROP TABLE leads;--"
    r = repo()
    r.create_lead(request(customer_name=payload))
    assert r.list_leads()[0]["cliente_nome"] == payload


# ------------------------------------------------------------ WhatsApp
def test_whatsapp_message_matches_persisted_record():
    lead = repo().create_lead(request())
    row = repo().list_leads()[0]
    url = lead_wa_link(lead)
    parsed = urlparse(url)
    assert parsed.scheme == "https" and parsed.netloc == "wa.me" and parsed.path == "/5511912345678"
    text = parse_qs(parsed.query)["text"][0]
    assert text == build_lead_message(lead)
    for expected in (row["protocolo"], row["cliente_nome"], row["produto_nome"], str(row["quantidade"]),
                     date.fromisoformat(row["data_desejada"]).strftime("%d/%m/%Y"), row["observacoes"]):
        assert expected in text


def test_whatsapp_encoding_of_special_characters():
    msg = "Olá & tchau #1 ?x=y\nlinha 2 🎂"
    url = build_wa_link("5511912345678", msg)
    assert "&" not in url.split("?text=")[1] and "#" not in url and "\n" not in url
    assert parse_qs(urlparse(url).query)["text"][0] == msg


def test_no_link_without_store_number():
    lead = repo().create_lead(request())
    assert lead_wa_link(replace(lead, store_whatsapp=None)) is None


def test_origin_is_sanitized():
    assert normalize_origin(" Instagram ") == "instagram"
    assert normalize_origin("<script>") == "script"
    assert normalize_origin(None) == "site"
    assert normalize_origin("x" * 100) == "x" * 40


# ------------------------------------------------------------ Supabase (cliente falso)
class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeRpc:
    def __init__(self, outcome):
        self.outcome = outcome

    def execute(self):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return _FakeResult(self.outcome)


class _FakeClient:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        return _FakeRpc(self.outcome)


class _ApiError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.message, self.code = message, code


def _rpc_row(**overrides):
    row = dict(id="7b2f", protocolo="DF-261107-ABC123", criado=True, produto_nome="Cupcakes decorados",
               unidade="caixa com 6", quantidade=2, data_desejada="2026-11-20", modalidade="Entrega",
               observacoes="x", cliente_nome=CUSTOMER_NAME, status="Novo", confeitaria_nome="Kika Cakes",
               confeitaria_whatsapp="5511912345678")
    row.update(overrides)
    return row


def test_supabase_uses_rpc_with_parameters():
    client = _FakeClient([_rpc_row()])
    lead = SupabaseRepository(client, "kika-cakes").create_lead(request())
    name, params = client.calls[0]
    assert name == "criar_lead"
    assert params["p_confeitaria_slug"] == "kika-cakes"
    assert params["p_cliente_whatsapp"] == CUSTOMER_PHONE
    assert params["p_origem"] == "instagram"
    assert lead.protocol == "DF-261107-ABC123" and lead.status == "Novo"


@pytest.mark.parametrize("error,expected", [
    (_ApiError("produto_indisponivel", "22023"), LeadValidationError),
    (_ApiError('new row violates check constraint "leads_cliente_whatsapp_check"', "23514"), LeadValidationError),
    (_ApiError("permission denied for table leads", "42501"), LeadPersistenceError),
    (ConnectionError("network down"), LeadPersistenceError),
])
def test_supabase_errors_are_translated(error, expected):
    with pytest.raises(expected):
        SupabaseRepository(_FakeClient(error), "kika-cakes").create_lead(request())


def test_supabase_empty_response_is_not_success():
    with pytest.raises(LeadPersistenceError):
        SupabaseRepository(_FakeClient([]), "kika-cakes").create_lead(request())


# ------------------------------------------------------------ fluxo completo (AppTest)
def _submit_valid(at):
    at.button(key="req_cupcakes").click().run()
    at.text_input(key="f_name").input(CUSTOMER_NAME)
    at.text_input(key="f_phone").input("(11) 98765-4321")
    at.date_input(key="f_date").set_value(date.today() + timedelta(days=4))
    at.text_area(key="f_notes").input("Sem lactose")
    at.checkbox(key="f_consent").check()
    next(b for b in at.button if b.label == "Enviar solicitação").click().run()
    assert not at.exception
    return at


def _link_buttons(at):
    return [el for el in at.get("link_button")]


def test_full_flow_persists_shows_link_and_admin_reads_after_restart(monkeypatch):
    at = AppTest.from_file(APP)
    at.query_params["origem"] = "instagram"
    at = _submit_valid(at.run(timeout=30))
    lead: Lead = at.session_state["last_lead"]
    assert any("Solicitação registrada!" in s.value for s in at.success)

    links = _link_buttons(at)
    assert len(links) == 1
    url = links[0].proto.url
    assert parse_qs(urlparse(url).query)["text"][0] == build_lead_message(lead)
    page_text = " ".join(m.value for m in at.markdown) + " ".join(c.value for c in at.caption)
    assert "foi enviada" not in page_text.lower()

    # "reinício": novo processo de script, nova instância do repositório
    database.SQLiteRepository  # noqa: B018
    rows = get_repository(config.load_settings()).list_leads()
    assert rows[0]["protocolo"] == lead.protocol and rows[0]["origem"] == "instagram"

    monkeypatch.setenv("ADMIN_PASSWORD", "senha-teste")
    admin = AppTest.from_file(ADMIN).run(timeout=30)
    admin.text_input[0].input("senha-teste")
    admin.button[0].click().run()
    assert not admin.exception
    df = admin.dataframe[0].value
    assert lead.protocol in df["Protocolo"].tolist()


def test_database_failure_does_not_show_success(monkeypatch):
    def boom(self, req):
        raise LeadPersistenceError("falha simulada")

    monkeypatch.setattr(SQLiteRepository, "create_lead", boom)
    at = _submit_valid(AppTest.from_file(APP).run(timeout=30))
    assert not at.success
    assert not _link_buttons(at)
    assert "last_lead" not in at.session_state
    assert any("Não conseguimos registrar" in e.value for e in at.error)


def test_unexpected_exception_does_not_show_success(monkeypatch):
    def boom(self, req):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(SQLiteRepository, "create_lead", boom)
    at = _submit_valid(AppTest.from_file(APP).run(timeout=30))
    assert not at.success and not _link_buttons(at)


def test_catalog_unavailable_when_database_not_configured(monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "supabase")
    at = AppTest.from_file(APP).run(timeout=30)
    assert not at.exception
    assert any("catálogo está indisponível" in e.value for e in at.error)
    assert not [b for b in at.button if b.label == "Solicitar orçamento"]


def test_admin_requires_login_and_public_page_has_no_lead_data():
    lead = repo().create_lead(request())
    admin = AppTest.from_file(ADMIN).run(timeout=30)  # sem ADMIN_PASSWORD
    assert any("Acesso bloqueado" in e.value for e in admin.error)
    assert not admin.dataframe

    vitrine = AppTest.from_file(APP).run(timeout=30)
    rendered = " ".join(str(el.value) for el in vitrine.markdown) + " ".join(str(e.value) for e in vitrine.caption)
    assert lead.protocol not in rendered and CUSTOMER_NAME not in rendered


def test_privacy_notice_page_and_form_link():
    page = AppTest.from_file(str(ROOT / "pages" / "privacidade.py")).run(timeout=30)
    assert not page.exception
    assert page.title[0].value == "Aviso de privacidade"
    at = AppTest.from_file(APP).run(timeout=30)
    at.button(key="req_cupcakes").click().run()
    assert any("Como usamos seus dados" in e.label for e in at.expander)
