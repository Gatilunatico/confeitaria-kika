"""'Esqueceu a senha?' do painel (Supabase Auth), com um cliente falso do Supabase.

Garantias testadas:
- a resposta ao pedir o e-mail é a mesma exista ou não a conta (não revela quem é cadastrado);
- o link/código é validado NO SERVIDOR (verify_otp) e o token sai do endereço logo depois;
- a troca exige senha forte e confirmação; a sessão de recuperação é encerrada em seguida;
- recuperar a senha NUNCA abre o painel: a pessoa precisa entrar de novo (o login confere o perfil).
"""

import time
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import ADMIN_APP

STRONG = "NovaSenhaKika2026"


class FakeAuth:
    def __init__(self, valid_token="tok-valido", valid_code="123456", update_error=None, reset_error=None):
        self.valid_token, self.valid_code = valid_token, valid_code
        self.update_error, self.reset_error = update_error, reset_error
        self.calls = []

    def reset_password_for_email(self, email, options=None):
        self.calls.append(("reset", email))
        if self.reset_error:
            raise self.reset_error

    def verify_otp(self, params):
        self.calls.append(("verify", dict(params)))
        ok = params.get("token_hash") == self.valid_token or (
            params.get("token") == self.valid_code and params.get("email") == "kika@teste.dev")
        if not ok:
            raise ValueError("Token has expired or is invalid")
        return SimpleNamespace(user=SimpleNamespace(id="user-kika"), session=object())

    def update_user(self, attrs):
        self.calls.append(("update", "password" in attrs))
        if self.update_error:
            raise self.update_error
        return SimpleNamespace(user=SimpleNamespace(id="user-kika"))

    def sign_out(self, options=None):
        self.calls.append(("sign_out",))

    def sign_in_with_password(self, creds):
        raise ValueError("Invalid login credentials")

    def get_user(self):
        return SimpleNamespace(user=None)


@pytest.fixture
def auth(monkeypatch):
    fake = FakeAuth()
    import services.supabase_client as supabase_client

    monkeypatch.setattr(supabase_client, "get_supabase_client", lambda settings: SimpleNamespace(auth=fake))
    for var in ("STORE_NAME", "PUBLIC_APP_URL", "ADMIN_PASSWORD", "SQLITE_PATH"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "synthetic-publishable-key")
    monkeypatch.setenv("STORE_SLUG", "kika-cakes")
    return fake


def settings():
    import config

    return config.load_settings()


# ================================================================ serviço
def test_reset_request_is_generic_and_normalizes_email(auth):
    from services.auth_service import request_password_reset

    state = {}
    request_password_reset(state, settings(), "  Kika@Teste.DEV ")
    assert auth.calls == [("reset", "kika@teste.dev")]


def test_reset_request_validates_email_and_has_cooldown(auth):
    from services.auth_service import AuthError, request_password_reset

    state = {}
    with pytest.raises(AuthError, match="e-mail válido"):
        request_password_reset(state, settings(), "não-é-email")
    request_password_reset(state, settings(), "kika@teste.dev")
    with pytest.raises(AuthError, match="Aguarde"):
        request_password_reset(state, settings(), "kika@teste.dev")
    assert len([c for c in auth.calls if c[0] == "reset"]) == 1


def test_reset_request_rate_limit_message(auth):
    from services.auth_service import AuthError, request_password_reset

    auth.reset_error = RuntimeError("email rate limit exceeded")
    with pytest.raises(AuthError, match="Muitos pedidos"):
        request_password_reset({}, settings(), "kika@teste.dev")


def test_invalid_or_expired_link_is_rejected_and_counts_as_attempt(auth):
    from services.auth_service import AuthError, recovery_active, start_password_recovery

    state = {}
    with pytest.raises(AuthError, match="inválido ou expirado"):
        start_password_recovery(state, settings(), token_hash="tok-falso")
    assert not recovery_active(state) and state["login_attempts"] == 1


def test_code_path_requires_email_and_six_digits(auth):
    from services.auth_service import AuthError, recovery_active, start_password_recovery

    with pytest.raises(AuthError, match="6 dígitos"):
        start_password_recovery({}, settings(), email="kika@teste.dev", code="12")
    state = {}
    start_password_recovery(state, settings(), email="kika@teste.dev", code="123 456")
    assert recovery_active(state)
    assert ("verify", {"email": "kika@teste.dev", "token": "123456", "type": "recovery"}) in auth.calls


def test_new_password_rules_and_success_never_open_the_panel(auth):
    from services.auth_service import (AuthError, complete_password_reset, is_admin_session, recovery_active,
                                       start_password_recovery)

    state = {"admin_ok": True}  # qualquer sessão anterior é descartada ao validar o link
    start_password_recovery(state, settings(), token_hash="tok-valido")
    assert "admin_ok" not in state
    with pytest.raises(AuthError, match="pelo menos 10"):
        complete_password_reset(state, "curta", "curta")
    with pytest.raises(AuthError, match="não são iguais"):
        complete_password_reset(state, STRONG, STRONG + "x")
    complete_password_reset(state, STRONG, STRONG)
    assert ("update", True) in auth.calls and ("sign_out",) in auth.calls
    assert not recovery_active(state) and not is_admin_session(state, settings())


def test_same_password_message(auth):
    from services.auth_service import AuthError, complete_password_reset, start_password_recovery

    auth.update_error = RuntimeError("New password should be different from the old password.")
    state = {}
    start_password_recovery(state, settings(), token_hash="tok-valido")
    with pytest.raises(AuthError, match="diferente da anterior"):
        complete_password_reset(state, STRONG, STRONG)


def test_recovery_window_expires(auth, monkeypatch):
    from services import auth_service

    state = {}
    auth_service.start_password_recovery(state, settings(), token_hash="tok-valido")
    monkeypatch.setattr(auth_service.time, "time", lambda: state["recovery_started_at"] + 16 * 60)
    assert not auth_service.recovery_active(state)
    with pytest.raises(auth_service.AuthError, match="tempo"):
        auth_service.complete_password_reset(state, STRONG, STRONG)


# ================================================================ tela (admin_app.py)
def open_login(**query):
    at = AppTest.from_file(ADMIN_APP, default_timeout=60)
    for k, v in query.items():
        at.query_params[k] = v
    return at.run()


def test_login_page_offers_forgot_password(auth):
    at = open_login()
    labels = [t.label for t in at.text_input]
    assert labels[:2] == ["E-mail", "Senha"]
    assert "E-mail cadastrado" in labels and "Código de 6 dígitos" in labels
    at.text_input(key="fp_email").input("kika@teste.dev")
    next(b for b in at.button if b.label == "Enviar link").click().run()
    assert any("Se este e-mail tiver acesso ao painel" in s.value for s in at.success)


def test_link_from_email_opens_new_password_form_and_cleans_url(auth):
    at = open_login(token_hash="tok-valido", type="recovery")
    assert not at.exception
    assert "token_hash" not in at.query_params  # o token sai do endereço
    assert [t.label for t in at.text_input] == ["Nova senha", "Repita a nova senha"]
    at.text_input(key="np_1").input(STRONG)
    at.text_input(key="np_2").input(STRONG)
    next(b for b in at.button if b.label == "Salvar nova senha").click().run()
    assert any("Senha alterada" in s.value for s in at.success)
    assert [t.label for t in at.text_input][:2] == ["E-mail", "Senha"]  # volta ao login, sem abrir o painel
    assert not at.metric


def test_expired_link_shows_error_and_login(auth):
    at = open_login(token_hash="tok-vencido", type="recovery")
    assert any("inválido ou expirado" in e.value for e in at.error)
    assert [t.label for t in at.text_input][:2] == ["E-mail", "Senha"]
    assert "token_hash" not in at.query_params


def test_recovery_session_does_not_unlock_admin_pages(auth):
    at = open_login(token_hash="tok-valido", type="recovery")
    at.switch_page("pages/admin/orders.py").run()
    assert not at.metric and at.title[0].value == "Painel administrativo"


def test_local_mode_has_no_email_reset(monkeypatch, tmp_path):
    for var in ("SUPABASE_URL", "SUPABASE_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", "senha-local-teste")
    at = open_login()
    assert [t.label for t in at.text_input] == ["Senha"]
    assert any("fale com o suporte" in c.value for c in at.caption)


def test_missing_supabase_secrets_is_not_reported_as_wrong_password(monkeypatch):
    """Painel publicado sem SUPABASE_URL/KEY nos Secrets: a mensagem não pode culpar a senha."""
    from services.auth_service import AuthError, login_supabase

    for var in ("SUPABASE_URL", "SUPABASE_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "supabase")
    monkeypatch.setattr("config.get_setting", lambda name, default=None: default if name not in (
        "DB_BACKEND",) else "supabase")
    state = {}
    with pytest.raises(AuthError) as exc:
        login_supabase(state, settings(), "kika@teste.dev", "qualquer")
    assert "não está configurado" in str(exc.value) and "senha inválid" not in str(exc.value)
    assert state.get("login_attempts", 0) == 0  # não conta como tentativa errada
