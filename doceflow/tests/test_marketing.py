"""Estúdio de Marketing: geração de posts, legendas, persistência e acesso."""

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from streamlit.testing.v1 import AppTest

import config
from services.repository import get_repository
from services.auth_service import session_token
from marketing.brand import COLORS, LOGO_PATH
from marketing.caption_generator import (
    TEMPLATE_TYPES,
    TONES,
    default_post_texts,
    generate_caption,
    load_template,
    product_photo,
    suggest_hashtags,
)
from services.product_service import SEED_PRODUCTS, find_product
from marketing.store import MarketingError, PostDraft, SQLiteMarketingStore, SupabaseMarketingStore
from marketing.post_generator import FORMATS, LAYOUTS, TEMPLATES, PostContent, fit_photo, render_post
from services.supabase_client import DatabaseConfigError, get_supabase_client

ROOT = Path(__file__).resolve().parents[1]
from tests.conftest import LOGIN, MARKETING_PAGE, open_app, open_page  # noqa: E402
PRODUCTS = list(SEED_PRODUCTS)
BEM_CASADO = find_product(PRODUCTS, "bem-casado")      # foto real
BOLO = find_product(PRODUCTS, "bolo-tradicional")     # só ilustração SVG (sem foto)


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "STORE_SLUG", "STORE_NAME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "mk.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", "senha-teste-mk")


def _intersects(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _content(product=BEM_CASADO, **over):
    texts = default_post_texts(product, "produto")
    texts.update(over)
    photo = over.pop("photo", product_photo(product))
    return PostContent(title=texts["title"], price=texts["price"], cta=texts["cta"], photo=photo,
                       fit=over.get("fit", "cover"))


def _assert_layout(result, fmt):
    w, h = FORMATS[fmt]
    margin = LAYOUTS[fmt]["margin"]
    boxes = result.boxes
    for name, box in boxes.items():
        assert margin - 8 <= box[0] and box[2] <= w - margin + 8, f"{name} fora da margem lateral: {box}"
        assert 0 <= box[1] and box[3] <= h, name
    names = list(boxes)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert not _intersects(boxes[a], boxes[b]), f"{a} sobrepõe {b}"
    if fmt == "story":  # fora das faixas da interface do Instagram
        for name, box in boxes.items():
            assert box[1] >= 240 and box[3] <= h - 240, f"{name} na faixa coberta do Story: {box}"


# ================================================================ geração de posts
@pytest.mark.parametrize("template", TEMPLATE_TYPES)
@pytest.mark.parametrize("fmt", ["feed", "story"])
def test_square_and_story_png_with_safe_layout(template, fmt):
    result = render_post(template, fmt, _content())
    img = Image.open(BytesIO(result.png))
    assert img.format == "PNG" and img.size == FORMATS[fmt]
    assert {"badge", "logo", "photo", "title", "price", "cta"} <= set(result.boxes)
    assert not result.truncated
    _assert_layout(result, fmt)


@pytest.mark.parametrize("size", [(3000, 800), (800, 3000), (1000, 1000), (37, 1200)])
@pytest.mark.parametrize("mode", ["cover", "contain"])
def test_photo_proportion_is_preserved(size, mode):
    src = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(src)
    r = min(size) // 3
    d.ellipse((size[0] // 2 - r, size[1] // 2 - r, size[0] // 2 + r, size[1] // 2 + r), fill="red")
    out = fit_photo(src, (952, 416), mode, "#000000")
    assert out.size == (952, 416)
    # o círculo continua circular (largura ≈ altura): nenhuma distorção
    red = [(x, y) for x in range(0, 952, 2) for y in range(0, 416, 2) if out.getpixel((x, y))[0] > 200
           and out.getpixel((x, y))[1] < 80]
    xs, ys = [p[0] for p in red], [p[1] for p in red]
    if red and min(xs) > 2 and max(xs) < 948 and min(ys) > 2 and max(ys) < 412:  # círculo inteiro visível
        assert abs((max(xs) - min(xs)) - (max(ys) - min(ys))) <= 6


@pytest.mark.parametrize("fmt", ["feed", "story"])
def test_long_title_shrinks_wraps_and_never_overlaps(fmt):
    long_title = "Bolo de Aniversário Decorado com Flores de Açúcar, Morangos Frescos e Muito Recheio de Ninho"
    result = render_post("novidade", fmt, _content(title=long_title))
    assert result.font_sizes["title"] < LAYOUTS[fmt]["title_sizes"][0]
    _assert_layout(result, fmt)


def test_absurd_title_is_truncated_and_reported():
    result = render_post("produto", "feed", _content(title="Supercalifragilístico " * 15))
    assert "title" in result.truncated
    _assert_layout(result, "feed")


@pytest.mark.parametrize("price", ["A partir de R$ 12.345.678,90 / caixa com 6 unidades decoradas",
                                   "R$ 1.000.000,00"])
def test_big_price_fits(price):
    for fmt in ("feed", "story"):
        result = render_post("promocao", fmt, _content(price=price))
        _assert_layout(result, fmt)
        box = result.boxes["price"]
        assert box[2] - box[0] <= FORMATS[fmt][0] - 2 * LAYOUTS[fmt]["margin"]


def test_product_without_photo_uses_logo_placeholder():
    assert product_photo(BOLO) is None
    result = render_post("novidade", "feed", _content(BOLO, photo=None))
    img = Image.open(BytesIO(result.png)).convert("RGB")
    assert img.size == (1080, 1080)
    _assert_layout(result, "feed")


def test_logo_file_is_untouched():
    before = LOGO_PATH.read_bytes()
    render_post("promocao", "story", _content())
    assert LOGO_PATH.read_bytes() == before


def test_empty_texts_are_skipped_without_errors():
    result = render_post("produto", "feed", _content(title="", price="", cta=""))
    assert "title" not in result.boxes and "cta" not in result.boxes


def test_text_contrast_is_readable():
    def lum(hex_color):
        rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        rgb = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]

    def ratio(a, b):
        la, lb = sorted([lum(a), lum(b)], reverse=True)
        return (la + 0.05) / (lb + 0.05)

    for t in TEMPLATES.values():
        assert ratio(t["texto"], t["fundo"]) >= 7          # título e textos grandes
        assert ratio(t["preco"], t["fundo"]) >= 3          # preço em fonte grande
        assert ratio(t["cta_texto"], t["cta_fundo"]) >= 3  # chamada em fonte grande e negrito


def test_invalid_template_or_format():
    with pytest.raises(ValueError):
        render_post("outro", "feed", _content())
    with pytest.raises(ValueError):
        render_post("produto", "reels", _content())


# ================================================================ legendas
@pytest.mark.parametrize("tone", list(TONES))
@pytest.mark.parametrize("kind", TEMPLATE_TYPES)
def test_caption_tones_have_cta_price_and_hashtags(kind, tone):
    caption = generate_caption(kind, BEM_CASADO, tone, link="https://exemplo.streamlit.app/?origem=instagram")
    assert "Bem Casado" in caption
    assert "A partir de R$ 6,00 / unidade" in caption and "Valor final confirmado" in caption
    assert "orçamento" in caption.lower() and "?origem=instagram" in caption
    assert "#kikacakes" in caption and "#docesfinos" in caption


def test_tones_produce_different_texts():
    texts = {generate_caption("produto", BEM_CASADO, t) for t in TONES}
    assert len(texts) == 3


def test_hashtags_are_relevant_and_unique():
    tags = suggest_hashtags(find_product(PRODUCTS, "docinhos-premium"), "promocao")
    assert len(tags) == len(set(tags)) <= 10
    assert "#docinhos" in tags and "#promocao" in tags and all(t.startswith("#") for t in tags)


def test_invalid_tone_or_template():
    with pytest.raises(ValueError):
        generate_caption("produto", BEM_CASADO, "sarcastico")
    with pytest.raises(ValueError):
        load_template("qualquer")


# ================================================================ persistência
def _store():
    settings = config.load_settings()
    repo = get_repository(settings)
    return SQLiteMarketingStore(settings, repo.get_store().id), repo


def _draft(**over):
    data = dict(produto_id=None, produto_nome="Bem Casado", template="produto", formato="feed",
                titulo="Bem Casado", preco_texto="A partir de R$ 6,00", cta="Peça seu orçamento",
                tom="amigavel", legenda="Legenda de teste", status="Rascunho")
    data.update(over)
    return PostDraft(**data)


def test_draft_is_saved_and_recovered_after_restart():
    store, _ = _store()
    png = render_post("produto", "feed", _content()).png
    post_id = store.save(_draft(), png)
    again, _ = _store()  # novo objeto = app reiniciado
    posts = again.list()
    assert [p["id"] for p in posts] == [post_id]
    assert posts[0]["status"] == "Rascunho" and posts[0]["legenda"] == "Legenda de teste"
    assert again.image(posts[0]["imagem_path"]) == png


def test_update_caption_and_status():
    store, _ = _store()
    post_id = store.save(_draft(), render_post("produto", "feed", _content()).png)
    store.update(post_id, _draft(legenda="Nova legenda", status="Pronto"))
    store.set_status(post_id, "Publicado manualmente")
    post = store.list()[0]
    assert post["legenda"] == "Nova legenda" and post["status"] == "Publicado manualmente"


def test_invalid_data_is_rejected():
    store, _ = _store()
    png = render_post("produto", "feed", _content()).png
    with pytest.raises(MarketingError):
        store.save(_draft(status="Publicado"), png)
    with pytest.raises(MarketingError):
        store.save(_draft(legenda="x" * 2201), png)
    with pytest.raises(MarketingError):
        store.save(_draft(), b"nao-e-png")
    assert store.list() == []


def test_image_path_traversal_is_blocked():
    store, _ = _store()
    with pytest.raises(MarketingError):
        store.image("outra-loja/../../mk.db")


# Supabase com cliente falso: Storage + tabela
class _Res:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, table):
        self.client, self.table = client, table

    def insert(self, row):
        self.client.calls.append(("insert", self.table, row))
        return self

    def __getattr__(self, name):
        return lambda *a, **k: self

    def execute(self):
        if self.client.fail_insert:
            raise RuntimeError("falha simulada")
        return _Res([{"id": "x"}])


class _Bucket:
    def __init__(self, client):
        self.client = client

    def upload(self, path, data, options):
        self.client.calls.append(("upload", path, options))

    def remove(self, paths):
        self.client.calls.append(("remove", paths))


class _Storage:
    def __init__(self, client):
        self.client = client

    def from_(self, bucket):
        self.client.calls.append(("bucket", bucket))
        return _Bucket(self.client)


class _Client:
    def __init__(self, fail_insert=False):
        self.calls, self.fail_insert = [], fail_insert
        self.storage = _Storage(self)

    def table(self, name):
        return _Query(self, name)


def test_supabase_saves_png_in_private_bucket_under_store_folder():
    client = _Client()
    store = SupabaseMarketingStore(client, "11111111-1111-1111-1111-111111111111")
    post_id = store.save(_draft(), render_post("produto", "feed", _content()).png)
    upload = next(c for c in client.calls if c[0] == "upload")
    assert upload[1] == f"11111111-1111-1111-1111-111111111111/{post_id}.png"
    assert upload[2]["content-type"] == "image/png"
    assert ("bucket", "marketing") in client.calls
    row = next(c for c in client.calls if c[0] == "insert")[2]
    assert row["confeitaria_id"] == "11111111-1111-1111-1111-111111111111" and row["status"] == "Rascunho"


def test_supabase_failed_insert_removes_uploaded_image():
    client = _Client(fail_insert=True)
    store = SupabaseMarketingStore(client, "11111111-1111-1111-1111-111111111111")
    with pytest.raises(MarketingError):
        store.save(_draft(), render_post("produto", "feed", _content()).png)
    assert any(c[0] == "remove" for c in client.calls)


def test_supabase_client_requires_configuration():
    with pytest.raises(DatabaseConfigError):
        get_supabase_client()


def test_migration_004_has_private_bucket_and_owner_policies():
    sql = (ROOT / "database" / "migrations" / "004_marketing.sql").read_text(encoding="utf-8")
    assert "values ('marketing', 'marketing', false" in sql
    assert "enable row level security" in sql
    assert "revoke all on public.marketing_posts from anon, authenticated" in sql
    for op in ("select", "insert", "update", "delete"):
        assert f"marketing_storage_owner_{op}" in sql
    assert "'Rascunho', 'Pronto', 'Publicado manualmente'" in sql


# ================================================================ página (AppTest)
def _logged_studio():
    """Sessão administrativa válida e Estúdio aberto pelo app completo."""
    at = open_app()
    at.session_state["admin_ok"] = True
    at.session_state["admin_binding"] = session_token(config.load_settings())
    at.run()
    at.switch_page(MARKETING_PAGE).run()
    return at


def test_unauthorized_access_is_blocked():
    at = open_page(MARKETING_PAGE)  # sem login: vai para o login
    assert at.title[0].value == "Painel administrativo"
    assert [t.label for t in at.text_input] == ["Senha"]
    assert not at.code and not at.get("download_button")


def test_forged_session_without_binding_is_blocked():
    at = open_app()
    at.session_state["admin_ok"] = True  # sem o vínculo da sessão: não basta
    at.run()
    at.switch_page(MARKETING_PAGE).run()
    assert at.title[0].value == "Painel administrativo" and not at.code


def test_full_studio_flow_generate_edit_save_download():
    at = _logged_studio()
    assert not at.exception
    at.selectbox(key="mk_product").set_value("bem-casado").run(timeout=60)
    at.radio(key="mk_format").set_value("story").run(timeout=60)
    at.selectbox(key="mk_template").set_value("promocao").run(timeout=60)
    at.text_input(key="mk_title_bem-casado_promocao").input("Bem Casado para o seu grande dia").run(timeout=60)
    caption_key = next(t.key for t in at.text_area if t.key.startswith("mk_caption_bem-casado_promocao"))
    at.text_area(key=caption_key).input("Legenda editada pela Kika #kikacakes").run(timeout=60)
    assert not at.exception
    assert "Legenda editada pela Kika" in at.code[0].value
    assert any(b.label == "Baixar PNG" for b in at.get("download_button"))
    at.button(key="mk_save").click().run(timeout=60)
    assert not at.exception
    assert any("Post salvo" in s.value for s in at.success)
    store, _ = _store()
    post = store.list()[0]
    assert post["formato"] == "story" and post["template"] == "promocao"
    assert post["titulo"] == "Bem Casado para o seu grande dia" and post["legenda"].startswith("Legenda editada")


def test_product_without_photo_in_studio():
    at = _logged_studio()
    at.selectbox(key="mk_product").set_value("bolo-tradicional").run(timeout=60)
    assert not at.exception
    assert at.radio(key="mk_photo_bolo-tradicional").options == ["Enviar outra foto", "Sem foto (usa o logo)"]


def test_small_photo_upscale_is_reported():
    tiny = Image.new("RGB", (150, 600), "white")
    cover = render_post("produto", "feed", _content(photo=tiny, fit="cover"))
    contain = render_post("produto", "feed", _content(photo=tiny, fit="contain"))
    assert cover.photo_upscale > 2 and contain.photo_upscale < cover.photo_upscale
    big = render_post("produto", "feed", _content(photo=Image.new("RGB", (2400, 1600), "white")))
    assert big.photo_upscale < 1
