"""API do app da confeiteira (doceflow/api): autenticação, autorização, marketing, erros.

O Supabase é trocado por um falso em memória que imita o RLS: cada token enxerga só a
confeitaria do próprio perfil. O RLS real é testado em test_app_mobile_postgres.py.
"""

import base64
import uuid
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

import api.auth as auth_mod  # noqa: E402
import api.marketing as mk  # noqa: E402
from api.main import create_app  # noqa: E402
from config import load_settings  # noqa: E402

STORE_A, STORE_B = str(uuid.uuid4()), str(uuid.uuid4())
USER_A, USER_B, USER_NOPROFILE = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
TOKENS = {"tok-dona-a-" + "a" * 30: USER_A, "tok-dona-b-" + "b" * 30: USER_B,
          "tok-sem-perfil-" + "c" * 30: USER_NOPROFILE}
TOKEN_A, TOKEN_B, TOKEN_NOPROFILE = list(TOKENS)
PROD_A, PROD_B = str(uuid.uuid4()), str(uuid.uuid4())
SCOPED = {"produtos", "product_images", "marketing_posts"}


def _png(size=(400, 300), color=(240, 200, 200)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class FakeDB:
    def __init__(self):
        self.tables = {
            "admin_profiles": [{"user_id": USER_A, "confeitaria_id": STORE_A, "papel": "proprietaria", "ativo": True},
                               {"user_id": USER_B, "confeitaria_id": STORE_B, "papel": "proprietaria", "ativo": True}],
            "confeitarias": [{"id": STORE_A, "slug": "kika-cakes", "nome": "Kika Cakes", "whatsapp": None, "ativo": True},
                             {"id": STORE_B, "slug": "outra", "nome": "Outra", "whatsapp": None, "ativo": True}],
            "produtos": [self._prod(PROD_A, STORE_A, "bolo-de-pote", "Bolo de Pote"),
                         self._prod(PROD_B, STORE_B, "bolo-b", "Bolo da B")],
            "product_images": [{"id": str(uuid.uuid4()), "produto_id": PROD_A, "confeitaria_id": STORE_A,
                                "storage_path": f"{STORE_A}/{PROD_A}/foto.png", "alt_text": "", "principal": True,
                                "ordem": 1}],
            "marketing_posts": [],
        }
        self.files = {("product-images", f"{STORE_A}/{PROD_A}/foto.png"): _png()}
        self.inserts = 0

    @staticmethod
    def _prod(pid, store, slug, nome):
        return {"id": pid, "confeitaria_id": store, "slug": slug, "nome": nome, "categoria": "Bolos",
                "descricao": "Bolo cremoso no pote.", "unidade": "unidade", "preco": 12, "tipo_preco": "a_partir_de",
                "disponivel": True, "imagem": None, "qtd_min": 1, "qtd_max": 50, "ordem": 1, "publicado": True,
                "destaque": False, "prazo_producao_dias": None}


class Query:
    def __init__(self, db, user, table):
        self.db, self.user, self.table = db, user, table
        self.filters, self.op, self.payload, self._limit, self._order = [], "select", None, None, None

    def select(self, *_):
        return self

    def eq(self, col, val):
        self.filters.append((col, val))
        return self

    def in_(self, col, vals):
        self.filters.append((col, set(vals)))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def update(self, row):
        self.op, self.payload = "update", row
        return self

    def _visible(self, row):
        """Imita o RLS: perfil só o próprio; tabelas da loja só da loja do perfil."""
        if self.table == "admin_profiles":
            return row["user_id"] == self.user
        if self.table in SCOPED:
            stores = {p["confeitaria_id"] for p in self.db.tables["admin_profiles"] if p["user_id"] == self.user}
            return row["confeitaria_id"] in stores
        return True

    def _match(self, row):
        return all((row.get(c) in v) if isinstance(v, set) else row.get(c) == v for c, v in self.filters)

    def execute(self):
        rows = self.db.tables[self.table]
        if self.op == "insert":
            if not self._visible(self.payload):
                raise PermissionError("row-level security")
            if any(r["id"] == self.payload["id"] for r in rows):
                raise DuplicateKey()
            row = {"status": "Rascunho", "created_at": f"2026-11-21T12:{self.db.inserts:02d}:00Z",
                   "updated_at": "2026-11-21T12:00:00Z", **self.payload}
            self.db.inserts += 1
            rows.append(row)
            return SimpleNamespace(data=[row])
        hits = [r for r in rows if self._visible(r) and self._match(r)]
        if self.op == "update":
            for r in hits:
                r.update(self.payload)
            return SimpleNamespace(data=hits)
        if self._order:
            col, desc = self._order
            hits = sorted(hits, key=lambda r: r.get(col) or 0, reverse=desc)
        return SimpleNamespace(data=hits[: self._limit] if self._limit else hits)


class DuplicateKey(Exception):
    code = "23505"


class Bucket:
    def __init__(self, db, user, name):
        self.db, self.user, self.name = db, user, name

    def _allowed(self, path):
        stores = {p["confeitaria_id"] for p in self.db.tables["admin_profiles"] if p["user_id"] == self.user}
        return path.split("/", 1)[0] in stores

    def upload(self, path, data, _opts=None):
        if not self._allowed(path):
            raise PermissionError("Unauthorized")
        self.db.files[(self.name, path)] = data

    def download(self, path):
        if self.name == "marketing" and not self._allowed(path):
            raise PermissionError("Unauthorized")
        return self.db.files[(self.name, path)]

    def remove(self, paths):
        for p in paths:
            self.db.files.pop((self.name, p), None)

    def get_public_url(self, path):
        return f"https://fake.supabase.co/storage/v1/object/public/{self.name}/{path}"


class FakeClient:
    def __init__(self, db, token):
        self.db, self.token = db, token
        self.user = TOKENS.get(token)
        self.auth = SimpleNamespace(get_user=self._get_user)
        self.storage = SimpleNamespace(from_=lambda name: Bucket(db, self.user, name))

    def _get_user(self, token):
        if token not in TOKENS:
            raise RuntimeError("invalid JWT")
        return SimpleNamespace(user=SimpleNamespace(id=TOKENS[token]))

    def table(self, name):
        return Query(self.db, self.user, name)


@pytest.fixture
def env(monkeypatch):
    db = FakeDB()
    settings = replace(load_settings(), db_backend="supabase", supabase_url="https://fake.supabase.co",
                       supabase_key="sb_publishable_fake", store_slug="kika-cakes",
                       public_app_url="https://vitrine.exemplo")
    made = []

    def make_client(s, token):
        assert s.supabase_key.startswith("sb_publishable")  # nunca uma chave privilegiada
        made.append(token)
        return FakeClient(db, token)

    monkeypatch.setattr(auth_mod, "user_client", make_client)
    monkeypatch.setattr(auth_mod, "load_settings", lambda: settings)
    mk._render_calls.clear()
    client = TestClient(create_app(), raise_server_exceptions=False)
    return SimpleNamespace(db=db, client=client, made=made, settings=settings)


def h(token, **extra):
    return {"Authorization": f"Bearer {token}", **extra}


ART = {"produto_id": PROD_A, "template": "produto", "formato": "feed", "tom": "amigavel"}


# ================================================================ autenticação e autorização
def test_health_needs_no_login_and_reveals_nothing(env):
    r = env.client.get("/v1/saude")
    assert r.status_code == 200 and r.json() == {"status": "ok", "versao": "1.0.0"}


@pytest.mark.parametrize("path,method", [("/v1/eu", "get"), ("/v1/marketing/opcoes", "get"),
                                         ("/v1/marketing/posts", "get"), ("/v1/marketing/previa", "post"),
                                         ("/v1/instagram/status", "get")])
def test_every_route_requires_token(env, path, method):
    r = env.client.post(path, json=ART) if method == "post" else env.client.get(path)
    assert r.status_code == 401 and r.json()["erro"]["codigo"] == "token_ausente"
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["Basic abc", "Bearer curto", "Bearer " + "x" * 30 + " espaco",
                                    "Token " + "a" * 40])
def test_malformed_token_rejected_before_calling_supabase(env, header):
    r = env.client.get("/v1/eu", headers={"Authorization": header})
    assert r.status_code == 401 and env.made == []


def test_unknown_token_rejected_by_supabase_auth(env):
    r = env.client.get("/v1/eu", headers=h("token-desconhecido-" + "z" * 30))
    assert r.status_code == 401 and r.json()["erro"]["codigo"] == "token_invalido"


def test_user_without_admin_profile_gets_403(env):
    r = env.client.get("/v1/eu", headers=h(TOKEN_NOPROFILE))
    assert r.status_code == 403 and r.json()["erro"]["codigo"] == "sem_permissao"


def test_owner_of_another_store_gets_403(env):
    """A API desta instalação só serve a confeitaria do STORE_SLUG (kika-cakes)."""
    r = env.client.get("/v1/eu", headers=h(TOKEN_B))
    assert r.status_code == 403


def test_me_returns_own_store(env):
    r = env.client.get("/v1/eu", headers=h(TOKEN_A))
    assert r.status_code == 200
    assert r.json() == {"usuario_id": USER_A, "confeitaria": {"id": STORE_A, "slug": "kika-cakes", "nome": "Kika Cakes"}}


def test_token_is_validated_on_every_request(env):
    env.client.get("/v1/eu", headers=h(TOKEN_A))
    env.client.get("/v1/eu", headers=h(TOKEN_A))
    assert env.made == [TOKEN_A, TOKEN_A]  # sem cache de sessão: token revogado para de valer na hora


def test_api_unavailable_without_supabase_config(env, monkeypatch):
    monkeypatch.setattr(auth_mod, "load_settings", lambda: replace(env.settings, supabase_url=None))
    r = env.client.get("/v1/eu", headers=h(TOKEN_A))
    assert r.status_code == 503 and "SUPABASE" not in r.text


# ================================================================ marketing
def test_options_list_accepted_values(env):
    r = env.client.get("/v1/marketing/opcoes", headers=h(TOKEN_A))
    body = r.json()
    assert set(body["templates"]) == {"produto", "promocao", "novidade"} and set(body["formatos"]) == {"feed", "story"}


def test_preview_renders_png_and_caption_without_saving(env):
    r = env.client.post("/v1/marketing/previa", json={**ART, "formato": "story"}, headers=h(TOKEN_A))
    assert r.status_code == 200
    body = r.json()
    png = base64.b64decode(body["imagem_png_base64"])
    assert png.startswith(b"\x89PNG") and Image.open(BytesIO(png)).size == (1080, 1920)
    assert "Bolo de Pote" in body["legenda"] and "https://vitrine.exemplo" in body["legenda"]
    assert body["textos"]["preco_texto"].startswith("A partir de")
    assert "sem_foto" not in body["avisos"]  # usou a foto principal do produto
    assert env.db.tables["marketing_posts"] == []


def test_preview_warns_when_product_has_no_photo(env):
    env.db.tables["product_images"].clear()
    r = env.client.post("/v1/marketing/previa", json=ART, headers=h(TOKEN_A))
    assert r.status_code == 200 and "sem_foto" in r.json()["avisos"]  # arte sai com o logo


def test_preview_without_photo_by_choice_has_no_warning(env):
    r = env.client.post("/v1/marketing/previa", json={**ART, "usar_foto": False}, headers=h(TOKEN_A))
    assert r.status_code == 200 and r.json()["avisos"] == []


def test_cannot_use_product_from_another_store(env):
    r = env.client.post("/v1/marketing/previa", json={**ART, "produto_id": PROD_B}, headers=h(TOKEN_A))
    assert r.status_code == 404 and r.json()["erro"]["codigo"] == "produto_nao_encontrado"


@pytest.mark.parametrize("override", [{"template": "inexistente"}, {"formato": "reels"}, {"tom": "bravo"},
                                      {"produto_id": "nao-e-uuid"}, {"titulo": "x" * 121}, {"extra": "x" * 301}])
def test_invalid_input_is_rejected_without_echoing_values(env, override):
    r = env.client.post("/v1/marketing/previa", json={**ART, **override}, headers=h(TOKEN_A))
    assert r.status_code == 422 and r.json()["erro"]["codigo"] == "dados_invalidos"
    assert "x" * 50 not in r.text and "nao-e-uuid" not in r.text


def test_save_post_requires_idempotency_key(env):
    r = env.client.post("/v1/marketing/posts", json=ART, headers=h(TOKEN_A))
    assert r.status_code == 422


def test_save_post_is_idempotent(env):
    headers = h(TOKEN_A, **{"Idempotency-Key": "toque-0001"})
    first = env.client.post("/v1/marketing/posts", json={**ART, "legenda": "Minha legenda"}, headers=headers)
    second = env.client.post("/v1/marketing/posts", json={**ART, "legenda": "Outra"}, headers=headers)
    assert first.status_code == 201 and first.json()["criado"] is True
    assert second.status_code == 200 and second.json()["criado"] is False
    assert second.json()["id"] == first.json()["id"]
    posts = env.db.tables["marketing_posts"]
    assert len(posts) == 1 and posts[0]["legenda"] == "Minha legenda" and posts[0]["confeitaria_id"] == STORE_A
    assert ("marketing", f"{STORE_A}/{posts[0]['id']}.png") in env.db.files


def test_same_key_from_another_user_does_not_collide(env):
    env.db.tables["admin_profiles"].append({"user_id": USER_NOPROFILE, "confeitaria_id": STORE_A,
                                            "papel": "equipe", "ativo": True})
    key = {"Idempotency-Key": "mesma-chave-01"}
    a = env.client.post("/v1/marketing/posts", json=ART, headers=h(TOKEN_A, **key)).json()["id"]
    b = env.client.post("/v1/marketing/posts", json=ART, headers=h(TOKEN_NOPROFILE, **key)).json()["id"]
    assert a != b and len(env.db.tables["marketing_posts"]) == 2


def test_list_posts_paginates(env):
    for i in range(5):
        env.client.post("/v1/marketing/posts", json=ART, headers=h(TOKEN_A, **{"Idempotency-Key": f"pagina-{i:04d}"}))
    r = env.client.get("/v1/marketing/posts?pagina=2&limite=2", headers=h(TOKEN_A)).json()
    assert r["total"] == 5 and len(r["itens"]) == 2 and r["pagina"] == 2
    assert env.client.get("/v1/marketing/posts?limite=101", headers=h(TOKEN_A)).status_code == 422


def test_change_status_and_download_image(env):
    pid = env.client.post("/v1/marketing/posts", json=ART,
                          headers=h(TOKEN_A, **{"Idempotency-Key": "status-0001"})).json()["id"]
    r = env.client.patch(f"/v1/marketing/posts/{pid}", json={"status": "Publicado manualmente"}, headers=h(TOKEN_A))
    assert r.status_code == 200 and env.db.tables["marketing_posts"][0]["status"] == "Publicado manualmente"
    img = env.client.get(f"/v1/marketing/posts/{pid}/imagem", headers=h(TOKEN_A))
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content.startswith(b"\x89PNG")
    assert "no-store" in img.headers["cache-control"]
    bad = env.client.patch(f"/v1/marketing/posts/{pid}", json={"status": "Apagado"}, headers=h(TOKEN_A))
    assert bad.status_code == 422


def test_other_store_cannot_see_or_change_posts(env):
    """Dona B com perfil válido mas de outra loja: a API desta instalação recusa (403)."""
    pid = env.client.post("/v1/marketing/posts", json=ART,
                          headers=h(TOKEN_A, **{"Idempotency-Key": "privado-0001"})).json()["id"]
    for call in (lambda: env.client.get(f"/v1/marketing/posts/{pid}/imagem", headers=h(TOKEN_B)),
                 lambda: env.client.patch(f"/v1/marketing/posts/{pid}", json={"status": "Pronto"}, headers=h(TOKEN_B)),
                 lambda: env.client.get("/v1/marketing/posts", headers=h(TOKEN_B))):
        assert call().status_code == 403
    assert env.db.tables["marketing_posts"][0]["status"] == "Rascunho"


def test_unknown_post_is_404(env):
    r = env.client.get(f"/v1/marketing/posts/{uuid.uuid4()}/imagem", headers=h(TOKEN_A))
    assert r.status_code == 404 and r.json()["erro"]["codigo"] == "post_nao_encontrado"


def test_render_rate_limit(env, monkeypatch):
    monkeypatch.setattr(mk, "RENDER_LIMIT", 2)
    codes = [env.client.post("/v1/marketing/previa", json={**ART, "usar_foto": False}, headers=h(TOKEN_A)).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]


# ================================================================ instagram e robustez
def test_instagram_reports_not_enabled(env):
    r = env.client.get("/v1/instagram/status", headers=h(TOKEN_A))
    assert r.status_code == 200 and r.json()["publicacao_automatica"] is False


def test_oversized_body_rejected(env):
    r = env.client.post("/v1/marketing/previa", content=b"{" + b" " * 70_000 + b"}",
                        headers=h(TOKEN_A, **{"Content-Type": "application/json"}))
    assert r.status_code == 413


def test_unexpected_error_hides_details(env, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("segredo interno: postgres://usuario:senha@host")
    monkeypatch.setattr(mk, "render_post", boom)
    r = env.client.post("/v1/marketing/previa", json=ART, headers=h(TOKEN_A))
    assert r.status_code == 500 and "segredo" not in r.text and r.json()["erro"]["codigo"] == "erro_interno"


def test_api_code_never_mentions_service_role_keys():
    from pathlib import Path

    for f in (Path(__file__).resolve().parents[1] / "api").glob("*.py"):
        text = f.read_text(encoding="utf-8").lower()
        assert "sb_secret" not in text and "service_role_key" not in text
