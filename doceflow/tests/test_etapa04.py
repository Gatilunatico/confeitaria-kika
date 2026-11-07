"""Etapa 04: painel administrativo (autenticação, leads, status, indicadores, produtos)."""

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import config
from database import AdminAccessError, SupabaseRepository, get_repository
from services.catalog import slugify, validate_product
from services.dashboard import compute_metrics, created_date_brt, filter_leads, period_range
from services.leads import LEAD_STATUSES, LeadRequest, LeadValidationError

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")
ADMIN = str(ROOT / "pages" / "admin.py")
PASSWORD = "senha-de-teste-123"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "STORE_NAME", "STORE_SLUG", "WHATSAPP_NUMBER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "painel.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)


def repo():
    return get_repository(config.load_settings())


def make_lead(r=None, phone="5511987650000", product="docinhos-tradicionais", qty=2, name="Cliente Teste"):
    r = r or repo()
    return r.create_lead(LeadRequest(customer_name=name, whatsapp=phone, product_slug=product, quantity=qty,
                                     desired_date=date.today() + timedelta(days=8), fulfillment="Retirada",
                                     notes="", consent=True, origin="site"))


def lead_id(protocol):
    return next(r["id"] for r in repo().list_leads() if r["protocolo"] == protocol)


# ================================================================ regras puras
def _row(status, created="2026-11-07T15:00:00+00:00"):
    return {"status": status, "created_at": created}


def test_metrics_and_conversion():
    rows = [_row("Novo"), _row("Novo"), _row("Orçamento enviado"), _row("Venda concluída"), _row("Perdido")]
    m = compute_metrics(rows)
    assert (m.total, m.new, m.quotes_sent, m.sold) == (5, 2, 1, 1)
    assert m.conversion_rate == pytest.approx(0.2)
    assert m.conversion_label == "20,0%"


def test_conversion_without_leads_is_dash():
    assert compute_metrics([]).conversion_label == "—"


def test_sale_only_counts_with_manual_status():
    # "Orçamento enviado" ou lead antigo nunca vira venda sozinho
    assert compute_metrics([_row("Orçamento enviado")] * 3).sold == 0


def test_filter_by_status_and_period():
    rows = [_row("Novo", "2026-11-01T12:00:00+00:00"), _row("Perdido", "2026-11-06T12:00:00+00:00"),
            _row("Novo", "2026-11-07T12:00:00+00:00")]
    assert len(filter_leads(rows, ["Novo"])) == 2
    assert len(filter_leads(rows, None, date(2026, 11, 5), date(2026, 11, 7))) == 2
    assert len(filter_leads(rows, ["Novo"], date(2026, 11, 5), None)) == 1


def test_created_date_uses_brasilia_time():
    # 02:00 UTC do dia 8 ainda é dia 7 em Brasília
    assert created_date_brt("2026-11-08T02:00:00+00:00") == date(2026, 11, 7)


def test_period_range():
    assert period_range("Últimos 7 dias", date(2026, 11, 7)) == (date(2026, 11, 1), date(2026, 11, 7))
    assert period_range("Todo o período", date(2026, 11, 7)) == (None, None)


def _product_form(**o):
    d = dict(name="Torta de limão", category="Tortas", description="", unit="unidade", price=60,
             price_type="a_partir_de", available=True, image=None, min_qty=1, max_qty=10, order=7)
    d.update(o)
    return d


def test_validate_product_ok_and_slug():
    data, errors = validate_product(_product_form())
    assert errors == {} and data["slug"] == "torta-de-limao" and data["price"] == 60.0
    assert slugify("Pão de mel & Cia") == "pao-de-mel-cia"


@pytest.mark.parametrize("override,field", [
    ({"name": "A"}, "name"), ({"category": ""}, "category"), ({"unit": ""}, "unit"),
    ({"price": -1}, "price"), ({"price": "abc"}, "price"), ({"min_qty": 5, "max_qty": 2}, "qty"),
    ({"price_type": "gratis"}, "price_type"), ({"image": "../../config.py"}, "image"),
    ({"description": "x" * 501}, "description"),
])
def test_validate_product_errors(override, field):
    _, errors = validate_product(_product_form(**override))
    assert field in errors


def test_validate_product_duplicate_and_on_request():
    _, errors = validate_product(_product_form(name="Cupcakes"), existing_slugs={"cupcakes"})
    assert "name" in errors
    data, errors = validate_product(_product_form(price_type="sob_consulta", price=99))
    assert not errors and data["price"] is None


# ================================================================ repositório SQLite
def test_status_update_persists_after_restart():
    lead = make_lead()
    repo().update_lead_status(lead_id(lead.protocol), "Em atendimento")
    row = next(r for r in get_repository(config.load_settings()).list_leads() if r["protocolo"] == lead.protocol)
    assert row["status"] == "Em atendimento" and row["status_atualizado_em"]


def test_invalid_status_and_unknown_lead():
    lead = make_lead()
    with pytest.raises(LeadValidationError):
        repo().update_lead_status(lead_id(lead.protocol), "Fechado")
    with pytest.raises(LeadValidationError):
        repo().update_lead_status("nao-existe", "Perdido")


def test_cannot_touch_other_store(monkeypatch):
    lead = make_lead()
    own_id = lead_id(lead.protocol)
    monkeypatch.setenv("STORE_SLUG", "outra")
    monkeypatch.setenv("STORE_NAME", "Outra")
    other = repo()
    assert other.list_leads() == []
    with pytest.raises(LeadValidationError):
        other.update_lead_status(own_id, "Venda concluída")
    kika_product = next(p for p in other.list_products())  # produtos da "outra"
    monkeypatch.setenv("STORE_SLUG", "kika-cakes")
    kika = repo()
    with pytest.raises(LeadValidationError):
        kika.update_product(kika_product.id, {"price": 1.0})
    assert next(r for r in kika.list_leads())["status"] == "Novo"


def test_product_create_and_update_reach_storefront():
    r = repo()
    data, _ = validate_product(_product_form())
    r.create_product(data)
    created = next(p for p in repo().list_products() if p.slug == "torta-de-limao")
    edit, _ = validate_product(_product_form(price=75.5, available=False), editing=True)
    repo().update_product(created.id, edit)
    updated = next(p for p in get_repository(config.load_settings()).list_products() if p.slug == "torta-de-limao")
    assert updated.price == 75.5 and updated.available is False


def test_sqlite_from_previous_stage_is_migrated(tmp_path, monkeypatch):
    path = tmp_path / "antigo.db"
    monkeypatch.setenv("SQLITE_PATH", str(path))
    r = repo()
    assert r.list_leads() == []
    with sqlite3.connect(path) as conn:  # recria a tabela leads exatamente como na etapa 03
        conn.execute("DROP TABLE leads")
        conn.execute("""CREATE TABLE leads (id TEXT PRIMARY KEY, protocolo TEXT, confeitaria_id TEXT, produto_id TEXT,
            produto_nome TEXT, unidade TEXT, quantidade INTEGER, data_desejada TEXT, modalidade TEXT,
            observacoes TEXT, cliente_nome TEXT, cliente_whatsapp TEXT, consentimento INTEGER,
            consentimento_em TEXT, origem TEXT,
            status TEXT CHECK (status IN ('Novo','Em contato','Orçamento enviado','Fechado','Perdido')),
            fingerprint TEXT, created_at TEXT, updated_at TEXT)""")
        conn.execute("""INSERT INTO leads VALUES ('L1','DF-1',(select id from confeitarias),(select id from produtos limit 1),
            'Cupcakes','cx',1,'2026-12-01','Retirada','','Ana','5511987650000',1,'x','site','Fechado','fp','2026-11-01','2026-11-01')""")
    rows = repo().list_leads()
    assert [r["status"] for r in rows] == ["Venda concluída"]
    make_lead()  # banco migrado continua aceitando novos leads
    assert len(repo().list_leads()) == 2


# ================================================================ Supabase (cliente falso)
class _Res:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, data):
        self._data = data

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def execute(self):
        return _Res(self._data)


class _Client:
    def __init__(self, data):
        self._data = data

    def table(self, _name):
        return _Query(self._data)


def test_supabase_owner_without_store_is_denied():
    with pytest.raises(AdminAccessError):
        SupabaseRepository.for_owner(_Client([]), "user-1")


def test_supabase_update_blocked_by_rls_is_not_success():
    repo_ = SupabaseRepository(_Client([{"id": "s1", "slug": "kika-cakes", "nome": "Kika", "whatsapp": None}]),
                               "kika-cakes")
    repo_.client = _Client([])  # update não retorna linhas (RLS filtrou)
    repo_.get_store = lambda: type("S", (), {"id": "s1"})()
    with pytest.raises(LeadValidationError):
        repo_.update_lead_status("x", "Perdido")


# ================================================================ painel (AppTest)
def open_admin(login=True, password=PASSWORD):
    at = AppTest.from_file(ADMIN).run(timeout=30)
    if login:
        at.text_input[0].input(password)
        at.button[0].click().run()
    assert not at.exception
    return at


def metric(at, label):
    return next(m.value for m in at.metric if m.label == label)


def test_no_admin_data_without_login():
    make_lead(name="Pessoa Sigilosa")
    at = open_admin(login=False)
    assert not at.metric and not at.dataframe
    rendered = " ".join(str(e.value) for e in at.markdown) + " ".join(str(e.value) for e in at.caption)
    assert "Pessoa Sigilosa" not in rendered


def test_admin_blocked_without_password_configured(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD")
    at = open_admin(login=False)
    assert any("Acesso bloqueado" in e.value for e in at.error)
    assert not at.metric


def test_login_lockout_after_failed_attempts():
    at = AppTest.from_file(ADMIN).run(timeout=30)
    for _ in range(5):
        at.text_input[0].input("errada")
        at.button[0].click().run()
    at.run()
    assert any("Muitas tentativas" in e.value for e in at.error)
    assert not at.text_input  # formulário some durante o bloqueio


def test_dashboard_identifies_new_leads_and_metrics_reflect_data():
    r = repo()
    a = make_lead(r, phone="5511987650001")
    make_lead(r, phone="5511987650002")
    c = make_lead(r, phone="5511987650003")
    r.update_lead_status(lead_id(a.protocol), "Orçamento enviado")
    r.update_lead_status(lead_id(c.protocol), "Venda concluída")
    at = open_admin()
    assert metric(at, "Total de leads") == "3"
    assert metric(at, "Leads novos") == "1"
    assert metric(at, "Orçamentos enviados") == "1"
    assert metric(at, "Vendas concluídas") == "1"
    assert metric(at, "Taxa de conversão") == "33,3%"
    assert any("1** lead(s) novo(s)" in i.value for i in at.info)
    df = at.dataframe[0].value
    assert df.iloc[0]["Status"] == "Novo"  # novos aparecem primeiro
    assert set(df.columns) >= {"Status", "Cliente", "Produto", "Data desejada", "WhatsApp", "Conversa"}


def test_status_filter():
    r = repo()
    a = make_lead(r, phone="5511987650001")
    make_lead(r, phone="5511987650002")
    r.update_lead_status(lead_id(a.protocol), "Perdido")
    at = open_admin()
    at.multiselect(key="flt_status").set_value(["Perdido"]).run()
    assert len(at.dataframe[0].value) == 1
    assert metric(at, "Total de leads") == "2"  # indicadores seguem o período, não o filtro de status


def test_period_filter_hides_old_leads():
    r = repo()
    make_lead(r)
    old = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(timespec="seconds")
    with sqlite3.connect(config.load_settings().sqlite_path) as conn:
        conn.execute("UPDATE leads SET created_at = ?", (old,))
    make_lead(r, phone="5511987650009")
    at = open_admin()
    at.selectbox(key="flt_period").set_value("Últimos 30 dias").run()
    assert metric(at, "Total de leads") == "1"


def test_update_status_via_panel_and_persist_after_restart():
    lead = make_lead()
    lid = lead_id(lead.protocol)
    at = open_admin()
    at.selectbox(key="sel_lead").set_value(lid).run()
    at.selectbox(key=f"new_status_{lid}").set_value("Em atendimento").run()
    at.button(key="save_status").click().run()
    assert not at.exception
    assert any("atualizado para **Em atendimento**" in s.value for s in at.success)
    again = open_admin()  # nova sessão = app reiniciado
    assert again.dataframe[0].value.iloc[0]["Status"] == "Em atendimento"


def test_sale_requires_manual_confirmation():
    lead = make_lead()
    lid = lead_id(lead.protocol)
    at = open_admin()
    at.selectbox(key=f"new_status_{lid}").set_value("Venda concluída").run()
    at.button(key="save_status").click().run()
    assert any("Marque a confirmação" in e.value for e in at.error)
    assert repo().list_leads()[0]["status"] == "Novo"
    at.checkbox(key=f"confirm_sale_{lid}").check().run()
    at.button(key="save_status").click().run()
    assert repo().list_leads()[0]["status"] == "Venda concluída"


def test_whatsapp_button_targets_customer_without_claiming_sent():
    make_lead(phone="5521998765432", name="Bruna Teste")
    at = open_admin()
    links = [b for b in at.get("link_button")]
    assert links and links[0].proto.url.startswith("https://wa.me/5521998765432?text=")
    assert any("não envia" in c.value for c in at.caption)


def _submit(at, label):
    next(b for b in at.button if b.label == label).click().run()
    assert not at.exception
    return at


def test_edit_product_via_panel_updates_storefront():
    pid = next(p.id for p in repo().list_products() if p.slug == "docinhos-tradicionais")
    at = open_admin()
    at.selectbox(key="sel_product").set_value(pid).run()
    at.number_input(key=f"edit_{pid}_price").set_value(55.0)
    at.checkbox(key=f"edit_{pid}_avail").uncheck()
    _submit(at, "Salvar produto")
    assert any("atualizado" in s.value for s in at.success)
    cup = next(p for p in repo().list_products() if p.slug == "docinhos-tradicionais")
    assert cup.price == 55.0 and not cup.available
    vitrine = AppTest.from_file(APP).run(timeout=30)
    assert vitrine.button(key="req_docinhos-tradicionais").disabled


def test_create_product_via_panel():
    at = open_admin()
    at.text_input(key="new_name").input("Torta de limão")
    at.text_input(key="new_cat").input("Tortas")
    at.text_input(key="new_unit").input("unidade")
    at.number_input(key="new_price").set_value(60.0)
    _submit(at, "Cadastrar produto")
    assert any("cadastrado" in s.value for s in at.success)
    assert any(p.slug == "torta-de-limao" for p in repo().list_products())


def test_invalid_product_shows_errors_and_saves_nothing():
    before = len(repo().list_products())
    at = open_admin()
    at.text_input(key="new_name").input("X")
    _submit(at, "Cadastrar produto")
    assert any("Confira os campos" in e.value for e in at.error)
    assert len(repo().list_products()) == before


def test_logout_hides_data():
    make_lead()
    at = open_admin()
    next(b for b in at.button if b.label == "Sair").click().run()
    at.run()
    assert not at.metric and not at.dataframe


def test_statuses_are_the_requested_ones():
    assert LEAD_STATUSES == ("Novo", "Em atendimento", "Orçamento enviado", "Venda concluída", "Perdido")
