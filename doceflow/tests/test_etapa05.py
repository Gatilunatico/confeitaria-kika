"""Regressions from the independent review against the integrated data model."""
from dataclasses import replace
from datetime import date, timedelta
import pytest
from config import load_settings
from database import get_repository
from services.auth import session_token
from services.leads import LeadRequest

@pytest.fixture
def qa_settings(tmp_path, monkeypatch):
    monkeypatch.delenv('SUPABASE_URL',raising=False)
    monkeypatch.delenv('SUPABASE_KEY',raising=False)
    monkeypatch.setenv('DB_BACKEND','sqlite')
    monkeypatch.setenv('SQLITE_PATH',str(tmp_path/'review.db'))
    monkeypatch.setenv('STORE_SLUG','qa-review-a')
    monkeypatch.setenv('ADMIN_PASSWORD','synthetic-review-password')
    return load_settings()


def test_admin_session_invalidates_on_actual_store_configuration(qa_settings):
    assert session_token(qa_settings) != session_token(replace(qa_settings, store_slug='qa-review-b'))


def test_public_lead_is_recovered_by_admin(qa_settings):
    public = get_repository(qa_settings)
    lead = public.create_lead(LeadRequest(
        customer_name='Cliente QA Regressao', whatsapp='5511987654321', product_slug='cupcakes',
        quantity=2, desired_date=date.today()+timedelta(days=7), fulfillment='Retirada', notes='', consent=True))
    records = get_repository(qa_settings).list_leads()
    assert any(row['protocolo'] == lead.protocol for row in records)


def test_settings_repr_does_not_expose_credentials(qa_settings):
    configured = replace(qa_settings, supabase_key='synthetic-key-private', admin_password='synthetic-password-private')
    assert 'synthetic-key-private' not in repr(configured)
    assert 'synthetic-password-private' not in repr(configured)


def test_supabase_login_is_bound_to_store_and_session_expiration(qa_settings, monkeypatch):
    from types import SimpleNamespace
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    import database

    local_repo = get_repository(qa_settings)
    lead = local_repo.create_lead(LeadRequest(
        customer_name='Cliente Auth Teste', whatsapp='5511987654321', product_slug='cupcakes',
        quantity=2, desired_date=date.today()+timedelta(days=5), fulfillment='Retirada', notes='', consent=True))
    class Auth:
        expired = False
        signed_out = False
        def sign_in_with_password(self, credentials):
            if credentials != {'email':'qa@example.test','password':'synthetic-valid-password'}:
                raise ValueError('Invalid credentials')
            return SimpleNamespace(user=SimpleNamespace(id='test-owner'))
        def get_user(self):
            if self.expired:
                raise ValueError('Expired session')
            return SimpleNamespace(user=SimpleNamespace(id='test-owner'))
        def sign_out(self):
            self.signed_out = True
    client = SimpleNamespace(auth=Auth())
    calls = []
    def for_owner(cls, auth_client, user_id, store_slug=None):
        calls.append((user_id,store_slug))
        assert auth_client is client
        assert user_id == 'test-owner'
        assert store_slug == 'qa-review-a'
        return local_repo
    monkeypatch.setattr(database,'get_supabase_client',lambda settings:client)
    monkeypatch.setattr(database.SupabaseRepository,'for_owner',classmethod(for_owner))
    monkeypatch.setenv('DB_BACKEND','supabase')
    monkeypatch.setenv('SUPABASE_URL','https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_KEY','synthetic-publishable-key')
    admin = str(Path(__file__).resolve().parents[1]/'pages/admin.py')
    at = AppTest.from_file(admin,default_timeout=60).run()
    assert [x.label for x in at.text_input] == ['E-mail','Senha']
    assert not at.dataframe
    at.text_input[0].input('qa@example.test')
    at.text_input[1].input('wrong')
    at.button[0].click().run()
    assert any('inválidos' in x.value for x in at.error)
    assert not at.dataframe
    at.text_input[1].input('synthetic-valid-password')
    at.button[0].click().run()
    assert not at.exception
    assert lead.protocol in at.dataframe[0].value['Protocolo'].tolist()
    assert len(calls) >= 2  # owner revalidated on the authenticated rerun
    client.auth.expired = True
    at.run()
    assert not at.exception
    assert not at.dataframe
    assert [x.label for x in at.text_input] == ['E-mail','Senha']
    assert client.auth.signed_out


def test_supabase_owner_lookup_filters_configured_store():
    from types import SimpleNamespace
    from database import SupabaseRepository, AdminAccessError
    class Query:
        def __init__(self): self.filters=[]
        def select(self,columns): return self
        def eq(self,key,value): self.filters.append((key,value)); return self
        def limit(self,count): return self
        def execute(self): return SimpleNamespace(data=[])
    query = Query()
    client = SimpleNamespace(table=lambda table:query)
    with pytest.raises(AdminAccessError):
        SupabaseRepository.for_owner(client,'owner-a','bakery-a')
    assert ('owner_user_id','owner-a') in query.filters
    assert ('slug','bakery-a') in query.filters
    assert ('ativo',True) in query.filters
