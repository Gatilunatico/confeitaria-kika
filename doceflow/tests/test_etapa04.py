from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from services.repository import Repository, indicators, STATUSES
from services.quotes import QuoteRequest, DuplicateQuoteError
from services.auth import authenticate, session_token
from config import load_settings

ADMIN = str(Path(__file__).resolve().parents[1] / 'pages/admin.py')

@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('SQLITE_PATH', str(tmp_path / 'admin.db'))
    monkeypatch.setenv('DB_BACKEND', 'sqlite')
    monkeypatch.setenv('STORE_ID', 'bakery-a')
    monkeypatch.setenv('ADMIN_PASSWORD', 'test-private-password')


def quote(**kwargs):
    values = dict(customer_name='Cliente Teste', whatsapp='5511987654321', product_id='cupcakes',
                  product_name='Cupcakes', quantity=2, unit='caixa', desired_date=date.today(),
                  fulfillment='Retirada', notes='Sem dados reais', consent=True)
    values.update(kwargs)
    return QuoteRequest(**values)


def login():
    at = AppTest.from_file(ADMIN, default_timeout=60).run(timeout=30)
    at.text_input[0].input('test-private-password')
    at.button[0].click().run()
    assert not at.exception
    return at


def test_auth_blocks_data_and_fake_legacy_session(monkeypatch):
    Repository().add(quote(customer_name='Cliente confidencial'))
    at = AppTest.from_file(ADMIN, default_timeout=60)
    at.session_state['admin_ok'] = True
    at.run(timeout=30)
    assert not at.metric and not at.dataframe
    assert not at.tabs
    at.text_input[0].input('errada')
    at.button[0].click().run()
    assert at.error[0].value == 'Senha incorreta.'
    monkeypatch.delenv('ADMIN_PASSWORD')
    at = AppTest.from_file(ADMIN, default_timeout=60).run()
    assert 'Acesso bloqueado' in at.error[0].value
    assert not at.metric


def test_auth_scope_and_rotation(monkeypatch):
    a = session_token(load_settings())
    assert authenticate('test-private-password', load_settings())
    monkeypatch.setenv('STORE_ID', 'bakery-b')
    assert session_token(load_settings()) != a
    monkeypatch.setenv('ADMIN_PASSWORD', 'changed')
    assert not authenticate('test-private-password', load_settings())


def test_restart_status_filters_and_metrics():
    repo = Repository()
    first = repo.add(quote(created_at=datetime(2026, 11, 1, 12)))
    second = repo.add(quote(desired_date=date.today()+timedelta(days=1), created_at=datetime(2026, 11, 2, 12)))
    assert indicators(repo.all())['Vendas concluídas'] == 0
    with pytest.raises(ValueError, match='manualmente'):
        repo.update_status(first.protocol, 'venda_concluida')
    for status in STATUSES:
        repo.update_status(first.protocol, status, confirm_sale=True)
        assert next(q for q in Repository().all() if q.protocol == first.protocol).status == status
    repo.update_status(first.protocol, 'venda_concluida', True)
    repo.update_status(second.protocol, 'orcamento_enviado')
    assert indicators(Repository().all()) == {'Total de leads':2, 'Leads novos':0, 'Orçamentos enviados':1, 'Vendas concluídas':1, 'Taxa de conversão':'50.0%'}
    assert len(repo.all(start=date(2026,11,1), end=date(2026,11,1))) == 1
    assert len(repo.all(status='orcamento_enviado')) == 1
    assert not repo.all(start=date(2026,11,3))
    with pytest.raises(ValueError):
        repo.all(start=date(2026,11,3), end=date(2026,11,1))
    with pytest.raises(ValueError):
        repo.update_status(first.protocol, 'invalido')
    with pytest.raises(DuplicateQuoteError):
        repo.add(quote())
    assert indicators([])['Taxa de conversão'] == '0.0%'


def test_tenant_isolation(monkeypatch):
    repo = Repository()
    first = repo.add(quote())
    product = repo.products()[0]
    repo.save_product(replace(product, price=999.0))
    monkeypatch.setenv('STORE_ID', 'bakery-b')
    other = Repository()
    assert other.all() == []
    assert next(p for p in other.products() if p.id == product.id).price != 999.0
    with pytest.raises(ValueError, match='não encontrada'):
        other.update_status(first.protocol, 'perdido')
    other.save_product(replace(product, name='Outro nome'))
    assert next(p for p in repo.products() if p.id == product.id).name == product.name


def test_product_persistence_public_catalog_and_validation():
    from services.catalog import list_products, get_product
    repo = Repository()
    product = repo.products()[0]
    repo.save_product(replace(product, price=87.5, available=False))
    assert not get_product(product.id).available
    assert get_product(product.id).price == 87.5
    repo.save_product(replace(product, id='novo-produto', name='Novo doce'))
    assert any(p.id == 'novo-produto' for p in list_products())
    assert len(Repository().products()) == 7
    for invalid in (replace(product, name=''), replace(product, price=-1), replace(product, price=float('nan')), replace(product, min_qty=8, max_qty=2)):
        with pytest.raises(ValueError):
            repo.save_product(invalid)


def test_admin_ui_manual_status_and_logout():
    lead = Repository().add(quote())
    at = login()
    assert at.metric[0].value == '1'
    assert at.metric[1].value == '1'
    assert len(at.dataframe[0].value) == 1
    at.selectbox[2].select('venda_concluida')
    next(b for b in at.button if b.label == 'Salvar status').click().run()
    assert any('manualmente' in e.value for e in at.error)
    at.checkbox[0].check()
    next(b for b in at.button if b.label == 'Salvar status').click().run()
    assert Repository().all()[0].status == 'venda_concluida'
    assert at.metric[3].value == '1'
    assert at.metric[4].value == '100.0%'
    assert 'wa.me/5511987654321' in str(at.get('link_button')[0].proto)
    next(b for b in at.button if b.label == 'Sair').click().run()
    assert not at.metric
    assert at.text_input[0].label == 'Senha'


def test_admin_ui_product_creation():
    at = login()
    next(t for t in at.text_input if t.label == 'Nome do produto').input('Trufa especial')
    next(t for t in at.text_input if t.label == 'Categoria').input('Doces')
    next(b for b in at.button if b.label == 'Salvar produto').click().run()
    assert not at.exception
    assert any(p.name == 'Trufa especial' for p in Repository().products())

def test_restart_in_fresh_process():
    import os
    import subprocess
    import sys
    lead = Repository().add(quote())
    Repository().update_status(lead.protocol, 'venda_concluida', True)
    source = "from services.repository import Repository; r=Repository(); assert len(r.all()) == 1; assert r.all()[0].status == 'venda_concluida'; print('persistencia confirmada')"
    result = subprocess.run([sys.executable, '-c', source], cwd=Path(ADMIN).parents[1], env=os.environ.copy(), capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert 'persistencia confirmada' in result.stdout


def test_admin_ui_filters():
    Repository().add(quote(created_at=datetime(2026, 11, 1, 12)))
    at = login()
    at.selectbox[0].select('perdido').run()
    assert at.metric[0].value == '0'
    assert not at.dataframe
    at.selectbox[0].select('todos').run()
    at.date_input[0].set_value(date(2026, 11, 2)).run()
    assert at.metric[0].value == '0'
    at.date_input[0].set_value(date(2026, 11, 1)).run()
    assert at.metric[0].value == '1'


def test_backend_fails_closed(monkeypatch):
    from database import DatabaseConfigError
    monkeypatch.setenv('DB_BACKEND', 'supabase')
    with pytest.raises(DatabaseConfigError):
        Repository()

