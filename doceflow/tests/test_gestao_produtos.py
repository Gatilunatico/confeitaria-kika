"""Etapa 3: gestão de produtos e fotos (cadastro, edição, publicação, exclusão e upload).

Telas testadas com o AppTest no SQLite local; a integração com o Supabase Storage é
testada com um cliente falso (as regras do banco estão em test_gestao_produtos_postgres).
"""

from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

import config
from services.image_service import MAX_IMAGES_PER_PRODUCT, ImageError, prepare_image
from services.product_service import validate_product
from services.quote_service import LeadRequest, LeadValidationError
from services.repository import PRODUCT_IN_USE, SupabaseRepository, get_repository
from tests.conftest import PRODUCTS, admin_login, open_page

CATALOG = "pages/public/catalog.py"
PASSWORD = "senha-produtos-teste"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for var in ("SUPABASE_URL", "SUPABASE_KEY", "STORE_NAME", "STORE_SLUG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "produtos.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", PASSWORD)


def repo():
    return get_repository(config.load_settings())


def by_slug(slug):
    return next((p for p in repo().list_products() if p.slug == slug), None)


def photo(fmt="JPEG", size=(2400, 1800), exif_gps=False) -> bytes:
    img = Image.new("RGB", size, (224, 98, 138))
    buf = BytesIO()
    kwargs = {}
    if exif_gps:
        exif = Image.Exif()
        exif[0x010F] = "CelularDaDona"  # fabricante
        exif[0x8825] = {1: "S", 2: (23.0, 33.0, 0.0)}  # GPS
        kwargs["exif"] = exif
    img.save(buf, format=fmt, **kwargs)
    return buf.getvalue()


def new_product_form(**o):
    f = dict(name="Torta de Limão", category="Tortas", description="Massa amanteigada e merengue.",
             price_type="a_partir_de", price=95.0, unit="kg", min_qty=1, max_qty=5, order=40,
             image=None, published=True, available=True, featured=True, production_days=3)
    f.update(o)
    return f


# ================================================================ validação
def test_validate_new_fields():
    data, errors = validate_product(new_product_form())
    assert errors == {} and data["featured"] is True and data["production_days"] == 3
    data, errors = validate_product(new_product_form(production_days=None, featured=False))
    assert errors == {} and data["production_days"] is None and data["featured"] is False
    for bad in (-1, 91, "abc"):
        assert "production_days" in validate_product(new_product_form(production_days=bad))[1]


# ================================================================ cadastro, edição, publicação (telas)
def _fill(at, prefix, **values):
    keys = {"name": "name", "category": "cat", "description": "desc", "unit": "unit"}
    for field, key in keys.items():
        if field in values:
            (at.text_area if field == "description" else at.text_input)(key=f"{prefix}_{key}").set_value(values[field])
    numbers = {"price": "price", "min_qty": "min", "max_qty": "max", "production_days": "days"}
    for field, key in numbers.items():
        if field in values:
            at.number_input(key=f"{prefix}_{key}").set_value(values[field])
    for field, key in {"featured": "feat", "published": "pub", "available": "avail"}.items():
        if field in values:
            at.checkbox(key=f"{prefix}_{key}").set_value(values[field])


def test_owner_creates_product_and_it_appears_in_catalog():
    at = admin_login(PASSWORD, PRODUCTS)
    _fill(at, "new", name="Torta de Limão", category="Tortas", description="Com merengue.", unit="kg",
          price=95.0, production_days=3, featured=True)
    next(b for b in at.button if b.label == "Cadastrar produto").click().run()
    assert not at.exception
    created = by_slug("torta-de-limao")
    assert created and created.featured and created.production_days == 3 and created.published
    assert at.session_state["sel_product"] == created.id  # o produto novo já fica aberto...
    assert at.session_state["product_tab"] == "Fotos"  # ...na aba de fotos, o próximo passo

    vitrine = open_page(CATALOG)
    keys = [b.key for b in vitrine.button]
    assert "req_torta-de-limao" in keys and "feat_torta-de-limao" in keys  # na lista e nos destaques
    assert any("Produção em cerca de 3 dias" in c.value for c in vitrine.caption)


def test_owner_creates_draft_hidden_from_visitors():
    at = admin_login(PASSWORD, PRODUCTS)
    _fill(at, "new", name="Bolo Rascunho", category="Bolos", unit="kg", price=80.0, published=False)
    next(b for b in at.button if b.label == "Cadastrar produto").click().run()
    assert by_slug("bolo-rascunho") and not by_slug("bolo-rascunho").published
    assert "req_bolo-rascunho" not in [b.key for b in open_page(CATALOG).button]


def test_invalid_product_is_not_saved():
    at = admin_login(PASSWORD, PRODUCTS)
    _fill(at, "new", name="X", category="", unit="kg")
    next(b for b in at.button if b.label == "Cadastrar produto").click().run()
    assert at.error and by_slug("x") is None


def test_owner_edits_price_details_and_catalog_updates():
    pid = by_slug("cupcake-tag").id
    at = admin_login(PASSWORD, PRODUCTS)
    at.selectbox(key="sel_product").set_value(pid).run()
    _fill(at, f"edit_{pid}", price=12.5, description="Cupcake com tag personalizada.", production_days=2,
          featured=True)
    next(b for b in at.button if b.label == "Salvar produto").click().run()
    assert not at.exception
    p = by_slug("cupcake-tag")
    assert (p.price, p.production_days, p.featured) == (12.5, 2, True)
    assert p.description == "Cupcake com tag personalizada."
    vitrine = open_page(CATALOG)
    assert any("12,50" in m.value for m in vitrine.markdown)
    assert "feat_cupcake-tag" in [b.key for b in vitrine.button]


def test_publish_and_unpublish_button():
    pid = by_slug("bem-casado").id
    at = admin_login(PASSWORD, PRODUCTS)
    at.selectbox(key="sel_product").set_value(pid).run()
    at.button(key=f"toggle_pub_{pid}").click().run()
    assert not by_slug("bem-casado").published
    assert "req_bem-casado" not in [b.key for b in open_page(CATALOG).button]
    at.button(key=f"toggle_pub_{pid}").click().run()
    assert by_slug("bem-casado").published
    assert "req_bem-casado" in [b.key for b in open_page(CATALOG).button]


def test_unavailable_product_shows_disabled_button():
    repo().update_product(by_slug("bem-casado").id, {"available": False})
    vitrine = open_page(CATALOG)
    assert vitrine.button(key="req_bem-casado").disabled


# ================================================================ exclusão
def test_delete_requires_confirmation():
    pid = by_slug("cupcake-tag").id
    at = admin_login(PASSWORD, PRODUCTS)
    at.selectbox(key="sel_product").set_value(pid).run()
    assert at.button(key=f"del_{pid}").disabled
    at.checkbox(key=f"del_confirm_{pid}").check().run()
    at.button(key=f"del_{pid}").click().run()
    assert not at.exception and by_slug("cupcake-tag") is None
    assert at.selectbox(key="sel_product").value != pid


def test_product_with_quotes_cannot_be_deleted():
    pid = by_slug("bem-casado").id
    repo().create_lead(LeadRequest("Ana Teste", "5511987650000", "bem-casado", 50,
                                   date.today() + timedelta(days=5), "Retirada", "", True))
    with pytest.raises(LeadValidationError, match="Despublique"):
        repo().delete_product(pid)
    at = admin_login(PASSWORD, PRODUCTS)
    at.selectbox(key="sel_product").set_value(pid).run()
    at.checkbox(key=f"del_confirm_{pid}").check().run()
    at.button(key=f"del_{pid}").click().run()
    assert any("Despublique" in e.value for e in at.error) and by_slug("bem-casado")


# ================================================================ fotos (serviço e repositório local)
def test_prepare_image_resizes_and_strips_metadata():
    data, ext, mime = prepare_image(photo(exif_gps=True))
    with Image.open(BytesIO(data)) as img:
        assert max(img.size) == 1600 and (ext, mime) == ("jpg", "image/jpeg")
        assert not img.getexif()  # sem fabricante e sem GPS
    for fmt, ext in (("PNG", "png"), ("WEBP", "webp")):
        assert prepare_image(photo(fmt, (300, 200)))[1] == ext


def test_rejected_files():
    for bad in (b"", b"<svg onload=alert(1)>", b"GIF89a" + b"0" * 100, b"\xff\xd8" + b"0" * (6 * 1024 * 1024)):
        with pytest.raises(ImageError):
            prepare_image(bad)


def test_upload_registers_metadata_and_first_photo_is_principal(tmp_path):
    p = by_slug("bem-casado")
    first = repo().add_product_image(p.id, photo(), "Bem-casado")
    second = repo().add_product_image(p.id, photo("PNG", (400, 300)))
    images = repo().list_product_images(p.id)
    assert [i["principal"] for i in images] == [True, False]
    assert first["storage_path"].startswith(f"{first['confeitaria_id']}/{p.id}/")
    assert Path(first["url"]).exists() and second["storage_path"].endswith(".png")
    assert by_slug("bem-casado").photo == first["url"]  # foto principal vai para a vitrine


def test_switch_principal_and_remove_promotes_next():
    p = by_slug("bem-casado")
    a = repo().add_product_image(p.id, photo())
    b = repo().add_product_image(p.id, photo())
    repo().set_principal_image(b["id"])
    assert by_slug("bem-casado").photo == b["url"]
    repo().delete_product_image(b["id"])
    assert not Path(b["url"]).exists()
    images = repo().list_product_images(p.id)
    assert [(i["id"], i["principal"]) for i in images] == [(a["id"], True)]


def test_photo_limit_per_product():
    p = by_slug("bem-casado")
    small = photo(size=(50, 50))
    for _ in range(MAX_IMAGES_PER_PRODUCT):
        repo().add_product_image(p.id, small)
    with pytest.raises(ImageError, match="no máximo"):
        repo().add_product_image(p.id, small)


def test_photo_must_belong_to_store_product():
    with pytest.raises(LeadValidationError):
        repo().add_product_image("00000000-0000-0000-0000-000000000000", photo())


def test_deleting_product_removes_its_files():
    p = by_slug("cupcake-tag")
    img = repo().add_product_image(p.id, photo())
    repo().delete_product(p.id)
    assert not Path(img["url"]).exists()


# ================================================================ fotos (telas)
def test_photos_tab_lists_and_removes_with_confirmation():
    p = by_slug("bem-casado")
    a = repo().add_product_image(p.id, photo())
    b = repo().add_product_image(p.id, photo())
    at = admin_login(PASSWORD, PRODUCTS)
    at.selectbox(key="sel_product").set_value(p.id).run()
    assert any("Fotos do produto" in m.value for m in at.markdown)
    at.button(key=f"main_{b['id']}").click().run()
    assert by_slug("bem-casado").photo == b["url"]
    at.button(key=f"delimg_{a['id']}").click().run()
    assert len(repo().list_product_images(p.id)) == 2  # ainda pede confirmação
    at.button(key=f"delimg_ok_{a['id']}").click().run()
    assert [i["id"] for i in repo().list_product_images(p.id)] == [b["id"]]


def test_photos_tab_without_photos_shows_uploader():
    p = by_slug("bem-casado")
    at = admin_login(PASSWORD, PRODUCTS)
    at.selectbox(key="sel_product").set_value(p.id).run()
    assert any("ainda não tem fotos" in i.value for i in at.info)
    assert not at.exception


def test_visitor_cannot_reach_product_management():
    at = open_page(PRODUCTS)
    assert at.title[0].value == "Painel administrativo"
    assert not any(b.label in ("Cadastrar produto", "Excluir produto") for b in at.button)


# ================================================================ Supabase (cliente falso)
class _Res:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, client, name):
        self.client, self.name, self.op = client, name, "select"

    def __getattr__(self, attr):
        def call(*args, **kwargs):
            if attr in ("insert", "update", "delete", "select"):
                self.op = attr
            self.client.calls.append((self.name, attr, args))
            return self
        return call

    def execute(self):
        err = self.client.fail.get((self.name, self.op))
        if err:
            raise err
        return _Res(self.client.data.get((self.name, self.op), [{"id": "novo-id"}]))


class _Bucket:
    def __init__(self, client):
        self.client = client

    def upload(self, path, data, options):
        self.client.calls.append(("storage", "upload", (path, options)))

    def remove(self, paths):
        self.client.calls.append(("storage", "remove", (paths,)))

    def get_public_url(self, path):
        return f"https://exemplo.supabase.co/storage/v1/object/public/product-images/{path}"


class _Client:
    def __init__(self, data=None, fail=None):
        self.data, self.fail, self.calls = data or {}, fail or {}, []
        self.storage = type("S", (), {"from_": lambda _s, bucket: _Bucket(self)})()

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params):
        self.calls.append(("rpc", name, (params,)))
        return _Query(self, f"rpc:{name}")


STORE = {"id": "11111111-1111-1111-1111-111111111111", "slug": "kika-cakes", "nome": "Kika", "whatsapp": None}
PID = "22222222-2222-2222-2222-222222222222"
ROW = {"id": PID, "slug": "bolo", "nome": "Bolo", "categoria": "Bolos", "descricao": "", "unidade": "kg",
       "preco": 80, "tipo_preco": "a_partir_de", "disponivel": True, "imagem": None, "qtd_min": 1, "qtd_max": 5,
       "ordem": 1, "publicado": True, "destaque": True, "prazo_producao_dias": 4}


def _img(i, principal, ordem):
    return {"id": f"img{i}", "produto_id": PID, "storage_path": f"{STORE['id']}/{PID}/img{i}.jpg",
            "alt_text": "", "principal": principal, "ordem": ordem}


def test_supabase_catalog_uses_principal_photo_url():
    client = _Client(data={("confeitarias", "select"): [STORE], ("produtos", "select"): [ROW],
                           ("product_images", "select"): [_img(1, False, 1), _img(2, True, 2)]})
    [p] = SupabaseRepository(client, "kika-cakes").list_products()
    assert p.photo.endswith(f"{PID}/img2.jpg") and p.featured and p.production_days == 4


def test_supabase_catalog_survives_missing_photos_table():
    client = _Client(data={("confeitarias", "select"): [STORE], ("produtos", "select"): [ROW]},
                     fail={("product_images", "select"): RuntimeError("tabela ausente")})
    [p] = SupabaseRepository(client, "kika-cakes").list_products()
    assert p.photo is None and p.name == "Bolo"


def test_supabase_create_and_update_send_new_columns():
    client = _Client(data={("confeitarias", "select"): [STORE], ("produtos", "insert"): [{"id": PID}]})
    r = SupabaseRepository(client, "kika-cakes")
    data, _ = validate_product(new_product_form())
    assert r.create_product(data) == PID
    insert = next(c for c in client.calls if c[:2] == ("produtos", "insert"))[2][0]
    assert insert["destaque"] is True and insert["prazo_producao_dias"] == 3
    assert insert["confeitaria_id"] == STORE["id"]  # sempre a confeitaria da sessão


def test_supabase_second_photo_is_not_principal_and_goes_to_store_folder():
    client = _Client(data={("confeitarias", "select"): [STORE], ("product_images", "select"): [_img(1, True, 1)],
                           ("product_images", "insert"): [{"id": "x"}]})
    row = SupabaseRepository(client, "kika-cakes").add_product_image(PID, photo(size=(100, 100)))
    assert row["principal"] is False and row["ordem"] == 2
    upload = next(c for c in client.calls if c[1] == "upload")
    assert upload[2][0].startswith(f"{STORE['id']}/{PID}/") and upload[2][1]["upsert"] == "false"


def test_supabase_photo_limit_checked_before_upload():
    client = _Client(data={("confeitarias", "select"): [STORE],
                           ("product_images", "select"): [_img(i, i == 0, i) for i in range(10)]})
    with pytest.raises(ImageError, match="no máximo"):
        SupabaseRepository(client, "kika-cakes").add_product_image(PID, photo(size=(100, 100)))
    assert not any(c[1] == "upload" for c in client.calls)


def test_supabase_principal_uses_atomic_rpc():
    client = _Client()
    SupabaseRepository(client, "kika-cakes").set_principal_image("img2")
    assert ("rpc", "definir_foto_principal", ({"p_image_id": "img2"},)) in client.calls


def test_supabase_delete_product_with_history_is_blocked():
    class _FkError(Exception):
        code = "23503"

    client = _Client(data={("confeitarias", "select"): [STORE], ("product_images", "select"): [_img(1, True, 1)]},
                     fail={("produtos", "delete"): _FkError("foreign key")})
    with pytest.raises(LeadValidationError) as exc:
        SupabaseRepository(client, "kika-cakes").delete_product(PID)
    assert str(exc.value) == PRODUCT_IN_USE
    assert not any(c[1] == "remove" for c in client.calls)  # as fotos ficam intactas


def test_supabase_delete_product_removes_storage_files():
    client = _Client(data={("confeitarias", "select"): [STORE], ("product_images", "select"): [_img(1, True, 1)],
                           ("produtos", "delete"): [{"id": PID}]})
    SupabaseRepository(client, "kika-cakes").delete_product(PID)
    removed = next(c for c in client.calls if c[1] == "remove")[2][0]
    assert removed == [f"{STORE['id']}/{PID}/img1.jpg"]
