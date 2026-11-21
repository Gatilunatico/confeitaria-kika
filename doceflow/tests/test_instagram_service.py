"""Serviço do Instagram: publicador e conexão OAuth, com uma Meta FALSA (httpx.MockTransport)
e o banco real da migração 014 (PostgreSQL 16). Nenhuma chamada sai para a Meta de verdade.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("pgserver")
httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from instagram_service.app import create_app  # noqa: E402
from instagram_service.config import ConfigError, InstagramConfig, load_config  # noqa: E402
from instagram_service.graph import GraphError, InstagramGraph  # noqa: E402
from instagram_service.publisher import Publisher  # noqa: E402
from instagram_service.store import Database, hash_state, to_jpeg  # noqa: E402
from tests.test_seguranca_postgres import OWNER_A, pg  # noqa: E402,F401

TOKEN = "IGAA-token-de-teste-" + "z" * 40


class FakeMeta:
    """Imita graph.instagram.com e api.instagram.com, guardando o que recebeu."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.container_status = ["IN_PROGRESS", "FINISHED"]
        self.publish_error: dict | None = None
        self.create_error: dict | None = None
        self.publish_network_error = False
        self.quota = (0, 100)
        self.recent: list[dict] = []
        self.published: list[str] = []
        self.account_type = "BUSINESS"
        self._n = 0

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(req)
        path = req.url.path
        if req.url.host == "api.instagram.com":
            return httpx.Response(200, json={"data": [{"access_token": "curto-" + "a" * 30, "user_id": "178414",
                                                       "permissions": "instagram_business_basic"}]})
        if path.endswith("/access_token") or path.endswith("/refresh_access_token"):
            return httpx.Response(200, json={"access_token": TOKEN, "token_type": "bearer", "expires_in": 5184000})
        if path.endswith("/me"):
            return httpx.Response(200, json={"user_id": "178414", "username": "kikacakes_confeitaria",
                                             "account_type": self.account_type})
        if path.endswith("/content_publishing_limit"):
            return httpx.Response(200, json={"data": [{"quota_usage": self.quota[0], "config": {"quota_total": self.quota[1]}}]})
        if path.endswith("/media_publish"):
            if self.publish_network_error:
                self.publish_network_error = False
                self.container_status = ["PUBLISHED"]
                raise httpx.ReadTimeout("caiu depois de pedir")
            if self.publish_error:
                return httpx.Response(400, json={"error": self.publish_error})
            self._n += 1
            media = f"1790000{self._n}"
            self.published.append(media)
            self.container_status = ["PUBLISHED"]
            return httpx.Response(200, json={"id": media})
        if path.endswith("/media") and req.method == "POST":
            if self.create_error:
                return httpx.Response(400, json={"error": self.create_error})
            return httpx.Response(200, json={"id": "container-1"})
        if path.endswith("/media") and req.method == "GET":
            return httpx.Response(200, json={"data": self.recent})
        if "container-" in path:
            status = self.container_status.pop(0) if len(self.container_status) > 1 else self.container_status[0]
            return httpx.Response(200, json={"status_code": status, "id": "container-1"})
        if path.split("/")[-1].startswith("1790000"):
            return httpx.Response(200, json={"permalink": "https://www.instagram.com/p/ABC123/"})
        return httpx.Response(404, json={"error": {"message": "rota falsa não mapeada", "code": 100}})

    def graph(self):
        return InstagramGraph(app_id="123", app_secret="segredo-do-app", redirect_uri="https://servico.exemplo/v1/instagram/callback",
                              client=httpx.Client(transport=httpx.MockTransport(self.handler)))

    def sent_tokens_in_urls(self) -> bool:
        return any(TOKEN in str(c.url) for c in self.calls if "access_token" not in c.url.path)


class FakeStorage:
    def __init__(self):
        self.calls = []

    def jpeg_url(self, store_id, pub_id, png_path):
        self.calls.append((store_id, pub_id, png_path))
        return f"https://projeto.supabase.co/storage/v1/object/sign/instagram-media/{store_id}/{pub_id}.jpg?token=x"


@pytest.fixture
def svc(pg):
    """Banco limpo de publicações a cada teste; conta conectada na Kika."""
    dsn = pg.get_uri()
    with psycopg.connect(dsn, autocommit=True) as c:
        c.execute("delete from public.instagram_publications")
        c.execute("delete from public.marketing_posts")
        c.execute("delete from public.instagram_accounts")
        c.execute("delete from vault.secrets")
        store = str(c.execute("select id from public.confeitarias where slug='kika-cakes'").fetchone()[0])
    db = Database(dsn)
    db.save_connection(store, "178414", "kikacakes_confeitaria", "business", TOKEN,
                       datetime.now(timezone.utc) + timedelta(days=60))
    meta = FakeMeta()
    storage = FakeStorage()
    pub = Publisher(db, meta.graph(), storage, sleep=lambda s: None, poll_tries=3)
    return SimpleNamespace(dsn=dsn, db=db, meta=meta, storage=storage, pub=pub, store=store)


def queue(svc, formato="feed", legenda="Bolo de pote! #kikacakes", max_tentativas=3):
    post, pub = uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(svc.dsn, autocommit=True) as c:
        c.execute("""insert into public.marketing_posts (id, confeitaria_id, produto_nome, template, formato, tom, legenda,
                     imagem_path) values (%s,%s,'Bolo','produto',%s,'amigavel',%s,%s)""",
                  (post, svc.store, formato, legenda, f"{svc.store}/{post}.png"))
        c.execute("""insert into public.instagram_publications (id, confeitaria_id, marketing_post_id, formato, legenda,
                     imagem_path, agendado_para, idempotency_key, max_tentativas)
                     values (%s,%s,%s,%s,%s,%s, now(), %s, %s)""",
                  (pub, svc.store, post, formato, legenda if formato == "feed" else "", f"{svc.store}/{post}.png",
                   f"teste-{pub.hex[:12]}", max_tentativas))
    return str(pub)


def row(svc, pub):
    with psycopg.connect(svc.dsn, autocommit=True) as c:
        cur = c.execute("""select status, ig_media_id, permalink, erro_codigo, tentativas, ig_container_id
                           from public.instagram_publications where id = %s""", (pub,))
        return dict(zip([d.name for d in cur.description], cur.fetchone()))


def events(svc, pub):
    with psycopg.connect(svc.dsn, autocommit=True) as c:
        return [r[0] for r in c.execute("select evento from public.instagram_publication_logs where publication_id = %s order by id",
                                        (pub,))]


def set_ready(svc, pub):
    with psycopg.connect(svc.dsn, autocommit=True) as c:
        c.execute("update public.instagram_publications set proxima_tentativa_em = now() - interval '1 s' where id = %s", (pub,))


# ================================================================ publicação
def test_feed_published_with_real_media_id_and_permalink(svc):
    pub = queue(svc)
    assert svc.pub.run_once("w1") == {"publicado": 1, "agendado": 0, "falhou": 0, "verificar": 0}
    r = row(svc, pub)
    assert (r["status"], r["ig_media_id"], r["permalink"]) == ("publicado", "17900001", "https://www.instagram.com/p/ABC123/")
    assert events(svc, pub) == ["container_criado", "publicacao_pedida", "publicado"]
    create = next(c for c in svc.meta.calls if c.url.path.endswith("/media") and c.method == "POST")
    form = parse_qs(create.content.decode())
    assert form["caption"] == ["Bolo de pote! #kikacakes"] and "media_type" not in form
    assert form["image_url"][0].startswith("https://")
    assert create.headers["authorization"] == f"Bearer {TOKEN}"
    assert not svc.meta.sent_tokens_in_urls()  # token só no cabeçalho


def test_story_uses_media_type_stories_without_caption(svc):
    pub = queue(svc, formato="story")
    svc.pub.run_once("w1")
    create = next(c for c in svc.meta.calls if c.url.path.endswith("/media") and c.method == "POST")
    form = parse_qs(create.content.decode())
    assert form["media_type"] == ["STORIES"] and "caption" not in form
    assert row(svc, pub)["status"] == "publicado"


def test_transient_error_retries_then_succeeds(svc):
    pub = queue(svc)
    svc.meta.create_error = {"message": "Service temporarily unavailable", "code": 2, "is_transient": True}
    svc.pub.run_once("w1")
    r = row(svc, pub)
    assert (r["status"], r["erro_codigo"], r["tentativas"]) == ("agendado", "meta_2", 1)
    svc.meta.create_error = None
    set_ready(svc, pub)
    svc.pub.run_once("w1")
    assert row(svc, pub)["status"] == "publicado"
    assert svc.meta.published == ["17900001"]


def test_permanent_error_fails_without_retry(svc):
    pub = queue(svc)
    svc.meta.create_error = {"message": "Only photo or video can be accepted as media type.", "code": 9004,
                             "error_subcode": 2207052}
    assert svc.pub.run_once("w1")["falhou"] == 1
    r = row(svc, pub)
    assert (r["status"], r["erro_codigo"]) == ("falhou", "meta_9004_2207052")
    assert svc.meta.published == []


def test_expired_token_marks_account_and_fails(svc):
    pub = queue(svc)
    svc.meta.create_error = {"message": "Error validating access token", "code": 190, "type": "OAuthException"}
    svc.pub.run_once("w1")
    assert row(svc, pub)["status"] == "falhou"
    with psycopg.connect(svc.dsn, autocommit=True) as c:
        assert c.execute("select status from public.instagram_accounts").fetchone()[0] == "erro"
    assert svc.db.token(svc.store) is None  # sem conta conectada, nada mais sai


def test_retries_stop_at_max_attempts(svc):
    pub = queue(svc, max_tentativas=2)
    svc.meta.create_error = {"message": "Please retry", "code": 1, "is_transient": True}
    svc.pub.run_once("w1")
    set_ready(svc, pub)
    svc.pub.run_once("w1")
    assert row(svc, pub)["status"] == "falhou"
    assert events(svc, pub) == ["nova_tentativa_agendada", "falhou"]


def test_daily_limit_waits_without_publishing(svc):
    pub = queue(svc)
    svc.meta.quota = (100, 100)
    svc.pub.run_once("w1")
    r = row(svc, pub)
    assert (r["status"], r["erro_codigo"]) == ("agendado", "limite_diario")
    assert svc.meta.published == []


def test_media_still_processing_is_rescheduled(svc):
    pub = queue(svc)
    svc.meta.container_status = ["IN_PROGRESS"]
    svc.pub.run_once("w1")
    r = row(svc, pub)
    assert (r["status"], r["erro_codigo"], r["ig_container_id"]) == ("agendado", "midia_processando", "container-1")
    svc.meta.container_status = ["FINISHED"]
    set_ready(svc, pub)
    svc.pub.run_once("w1")
    assert row(svc, pub)["status"] == "publicado"
    creates = [c for c in svc.meta.calls if c.url.path.endswith("/media") and c.method == "POST"]
    assert len(creates) == 1  # reaproveitou o container: não criou outro


def test_network_drop_after_publish_does_not_duplicate(svc):
    """A rede cai DEPOIS de pedir a publicação: o serviço pergunta à Meta em vez de publicar de novo."""
    pub = queue(svc, legenda="Legenda única 123")
    svc.meta.container_status = ["FINISHED"]
    svc.meta.publish_network_error = True
    svc.meta.recent = [{"id": "17955555", "caption": "Legenda única 123",
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000"),
                        "permalink": "https://www.instagram.com/p/XYZ/"}]
    svc.pub.run_once("w1")
    r = row(svc, pub)
    assert (r["status"], r["ig_media_id"]) == ("publicado", "17955555")
    assert svc.meta.published == []  # nenhum segundo media_publish


def test_crash_after_publish_without_match_goes_to_verify(svc):
    """Retomada de item travado cujo container já foi publicado, sem como confirmar qual mídia."""
    pub = queue(svc)
    with psycopg.connect(svc.dsn, autocommit=True) as c:
        c.execute("""update public.instagram_publications set status = 'publicando', ig_container_id = 'container-1',
                     bloqueado_em = now() - interval '1 hour' where id = %s""", (pub,))
    svc.meta.container_status = ["PUBLISHED"]
    assert svc.pub.run_once("w2")["verificar"] == 1
    r = row(svc, pub)
    assert (r["status"], r["ig_media_id"]) == ("verificar", None)  # nunca "publicado" sem prova
    assert svc.meta.published == []


def test_disconnected_account_fails_clearly(svc):
    pub = queue(svc)
    with psycopg.connect(svc.dsn, autocommit=True) as c:
        c.execute("update public.instagram_accounts set status = 'desconectado'")
    svc.pub.run_once("w1")
    r = row(svc, pub)
    assert (r["status"], r["erro_codigo"]) == ("falhou", "instagram_desconectado")
    assert svc.meta.calls == []


def test_token_refresh_before_expiry(svc):
    with psycopg.connect(svc.dsn, autocommit=True) as c:
        c.execute("update public.instagram_accounts set token_expira_em = now() + interval '3 days'")
    assert svc.pub.refresh_tokens() == 1
    _, _, expires = svc.db.token(svc.store)
    assert expires > datetime.now(timezone.utc) + timedelta(days=50)


def test_png_becomes_jpeg_without_alpha():
    buf = BytesIO()
    Image.new("RGBA", (40, 40), (224, 98, 138, 128)).save(buf, "PNG")
    jpeg = to_jpeg(buf.getvalue())
    img = Image.open(BytesIO(jpeg))
    assert img.format == "JPEG" and img.mode == "RGB" and "exif" not in img.info


def test_graph_error_classification():
    def resp(status, err):
        return httpx.Response(status, json={"error": err})
    from instagram_service.graph import _classify
    assert _classify(resp(400, {"code": 190})).auth
    assert _classify(resp(400, {"code": 4})).rate_limited
    assert _classify(resp(400, {"code": 9, "error_subcode": 2207042})).transient
    assert _classify(resp(500, {"code": 1})).transient
    assert not _classify(resp(400, {"code": 100})).transient


# ================================================================ conexão (OAuth)
CFG = InstagramConfig(app_id="123", app_secret="segredo-do-app", redirect_uri="https://servico.exemplo/v1/instagram/callback",
                      graph_version="v23.0", db_url="postgresql://x", supabase_url="https://p.supabase.co",
                      service_key="sb_secret_x")


@pytest.fixture
def oauth(svc):
    with psycopg.connect(svc.dsn, autocommit=True) as c:
        c.execute("delete from public.instagram_accounts")
        c.execute("delete from vault.secrets")
        c.execute("delete from public.instagram_oauth_states")

    def resolver(authorization):
        from api.errors import ApiError
        if authorization != "Bearer token-da-dona-" + "d" * 30:
            raise ApiError(401, "token_invalido", "Sessão inválida.")
        return SimpleNamespace(user_id=str(OWNER_A), store=SimpleNamespace(id=svc.store))

    client = TestClient(create_app(cfg=CFG, db=svc.db, graph=svc.meta.graph(), admin_resolver=resolver),
                        raise_server_exceptions=False)
    return SimpleNamespace(client=client, svc=svc, auth={"Authorization": "Bearer token-da-dona-" + "d" * 30})


def test_connect_requires_admin_login(oauth):
    assert oauth.client.get("/v1/instagram/conexao").status_code == 401


def test_full_oauth_flow_stores_token_in_vault(oauth):
    r = oauth.client.get("/v1/instagram/conexao", headers=oauth.auth)
    url = urlparse(r.json()["url"])
    q = parse_qs(url.query)
    assert (url.scheme, url.netloc, url.path) == ("https", "www.instagram.com", "/oauth/authorize")
    assert q["scope"] == ["instagram_business_basic,instagram_business_content_publish"]
    assert q["redirect_uri"] == [CFG.redirect_uri] and "client_secret" not in q
    state = q["state"][0]
    cb = oauth.client.get("/v1/instagram/callback", params={"code": "codigo-da-meta#_", "state": state})
    assert cb.status_code == 200 and "conectado" in cb.text and TOKEN not in cb.text
    with psycopg.connect(oauth.svc.dsn, autocommit=True) as c:
        acc = c.execute("select status, username, account_type, token_vault_id is not null from public.instagram_accounts").fetchone()
        assert acc == ("conectado", "kikacakes_confeitaria", "business", True)
        assert c.execute("select decrypted_secret from vault.decrypted_secrets").fetchone()[0] == TOKEN
        # o state é guardado só como hash
        assert c.execute("select count(*) from public.instagram_oauth_states where nonce_hash = %s",
                         (hash_state(state),)).fetchone()[0] == 1
    exchange = next(c for c in oauth.svc.meta.calls if c.url.host == "api.instagram.com")
    assert parse_qs(exchange.content.decode())["code"] == ["codigo-da-meta"]  # "#_" da Meta removido
    again = oauth.client.get("/v1/instagram/callback", params={"code": "codigo-da-meta", "state": state})
    assert again.status_code == 400 and "já foi usado" in again.text  # state de uso único


def test_callback_rejects_unknown_state_and_cancel(oauth):
    assert "vencido" in oauth.client.get("/v1/instagram/callback", params={"code": "x", "state": "inventado"}).text
    assert "cancelada" in oauth.client.get("/v1/instagram/callback", params={"error": "access_denied"}).text
    assert oauth.svc.db.token(oauth.svc.store) is None


def test_personal_account_is_not_eligible(oauth):
    oauth.svc.meta.account_type = "PERSONAL"
    state = parse_qs(urlparse(oauth.client.get("/v1/instagram/conexao", headers=oauth.auth).json()["url"]).query)["state"][0]
    r = oauth.client.get("/v1/instagram/callback", params={"code": "c", "state": state})
    assert r.status_code == 400 and "profissionais" in r.text
    assert oauth.svc.db.token(oauth.svc.store) is None


def test_config_requires_https_redirect_and_secrets():
    with pytest.raises(ConfigError, match="Faltam"):
        load_config({})
    env = {k: "x" for k in ("INSTAGRAM_APP_ID", "INSTAGRAM_APP_SECRET", "SUPABASE_DB_URL", "SUPABASE_URL",
                            "SUPABASE_SERVICE_KEY")}
    with pytest.raises(ConfigError, match="https"):
        load_config({**env, "INSTAGRAM_REDIRECT_URI": "http://inseguro"})
    cfg = load_config({**env, "INSTAGRAM_REDIRECT_URI": "https://ok"})
    assert "segredo" not in repr(cfg) and "x" not in repr(cfg).split("app_id")[0]


def test_meta_error_text_never_contains_token():
    meta = FakeMeta()
    meta.create_error = {"message": "bad", "code": 100}
    g = meta.graph()
    with pytest.raises(GraphError) as e:
        g.create_container("1", TOKEN, "https://x/y.jpg", "c", False)
    assert TOKEN not in str(e.value) and TOKEN not in json.dumps(vars(e.value), default=str)
