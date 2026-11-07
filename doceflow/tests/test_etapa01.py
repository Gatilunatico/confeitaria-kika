from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import config
from database import check_connection
from services.whatsapp import build_wa_link, normalize_phone

APP_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def sqlite_env(tmp_path, monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "WHATSAPP_NUMBER", "ADMIN_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))


def test_normalize_phone():
    assert normalize_phone("+55 (11) 99999-9999") == "5511999999999"


def test_build_wa_link_encodes_message():
    url = build_wa_link("5511999999999", "Olá, quero um bolo!")
    assert url == "https://wa.me/5511999999999?text=Ol%C3%A1%2C%20quero%20um%20bolo%21"


def test_build_wa_link_rejects_invalid_phone():
    with pytest.raises(ValueError):
        build_wa_link("123")


def test_sqlite_backend_connects(sqlite_env):
    status = check_connection(config.load_settings())
    assert status.ok and status.backend == "sqlite"


def test_supabase_without_credentials_fails_safely(sqlite_env, monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "supabase")
    status = check_connection(config.load_settings())
    assert not status.ok
    assert "SUPABASE_URL" in status.detail


def test_app_renders_without_errors(sqlite_env):
    at = AppTest.from_file(str(APP_DIR / "app.py")).run(timeout=30)
    assert not at.exception
    # A partir da etapa 02 o título da vitrine é o nome da confeitaria (STORE_NAME).
    assert at.title[0].value == "Kika Cakes"


def test_admin_blocked_without_password(sqlite_env):
    at = AppTest.from_file(str(APP_DIR / "pages" / "admin.py")).run(timeout=30)
    assert not at.exception
    assert "Acesso bloqueado" in at.error[0].value


def test_admin_login(sqlite_env, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "senha-de-teste")
    at = AppTest.from_file(str(APP_DIR / "pages" / "admin.py")).run(timeout=30)
    at.text_input[0].input("errada")
    at.button[0].click().run()
    assert "Senha incorreta." in at.error[0].value
    at.text_input[0].input("senha-de-teste")
    at.button[0].click().run()
    assert at.success[0].value == "Acesso liberado."
