"""Nova estrutura: supabase_client, templates, geradores de legenda/post e página de marketing."""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

from services.caption_generator import TEMPLATE_TYPES, generate_caption, load_template
from services.catalog import SEED_PRODUCTS, find_product
from services.post_generator import generate_post
from supabase_client import DatabaseConfigError, get_supabase_client

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = list(SEED_PRODUCTS)


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "mk.db"))


def test_structure_files_exist():
    for rel in ("app.py", "database.py", "supabase_client.py", "pages/admin.py", "pages/marketing.py",
                "services/whatsapp.py", "services/post_generator.py", "services/caption_generator.py",
                "templates/promocao.json", "templates/produto.json", "templates/novidade.json",
                "assets/logos/logo-kika-cakes.png", "assets/fonts", "requirements.txt"):
        assert (ROOT / rel).exists(), rel


def test_supabase_client_requires_configuration():
    with pytest.raises(DatabaseConfigError):
        get_supabase_client()


@pytest.mark.parametrize("kind", TEMPLATE_TYPES)
def test_templates_have_required_fields(kind):
    t = load_template(kind)
    assert {"tipo", "nome", "titulo", "chamada", "hashtags", "cores"} <= set(t)
    assert t["tipo"] == kind


def test_caption_uses_starting_price_and_link():
    p = find_product(PRODUCTS, "bem-casado")
    caption = generate_caption("promocao", p, "Válido até sexta", "https://exemplo.streamlit.app/?origem=instagram")
    assert "Bem Casado" in caption and "a partir de R$ 6,00 / unidade" in caption
    assert "Válido até sexta" in caption and "?origem=instagram" in caption and "#kikacakes" in caption


def test_unknown_template_is_rejected():
    with pytest.raises(ValueError):
        load_template("qualquer")


@pytest.mark.parametrize("slug", ["bem-casado", "bolo-tradicional"])  # foto real e ilustração SVG
def test_post_is_1080_png(slug):
    png = generate_post("novidade", find_product(PRODUCTS, slug))
    img = Image.open(BytesIO(png))
    assert img.format == "PNG" and img.size == (1080, 1080)


def test_marketing_requires_admin_login():
    at = AppTest.from_file(str(ROOT / "pages" / "marketing.py")).run(timeout=30)
    assert not at.exception
    assert any("Entre primeiro no painel" in w.value for w in at.warning)
    assert not at.code


def test_marketing_generates_caption_after_login():
    at = AppTest.from_file(str(ROOT / "pages" / "marketing.py"))
    at.session_state["admin_ok"] = True
    at.run(timeout=30)
    assert not at.exception
    assert "a partir de" in at.code[0].value
