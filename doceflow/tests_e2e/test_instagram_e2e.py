"""Ponta a ponta do marketing + Instagram contra um Supabase LOCAL (Auth, PostgREST, Storage, Vault).

A Meta é SIMULADA (FakeMeta, de tests/test_instagram_service.py): nada é publicado de verdade.
Tudo o mais é real: login da dona, API de marketing, Storage, funções da migração 014, Vault e
o publicador. Não roda no pytest normal; precisa das variáveis E2E_* (ver docs/app_mobile/instagram.md).
Recusa rodar contra o projeto de produção.
"""

import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

E = {k: os.environ.get(k, "") for k in ("E2E_SUPABASE_URL", "E2E_PUBLISHABLE_KEY", "E2E_SERVICE_KEY", "E2E_DB_URL",
                                         "E2E_OWNER_EMAIL", "E2E_OWNER_PASS", "E2E_OTHER_EMAIL", "E2E_OTHER_PASS")}
pytestmark = pytest.mark.skipif(not all(E.values()), reason="Supabase local não configurado (variáveis E2E_*)")
if "dfimrkfcudidosdldsjv" in E["E2E_SUPABASE_URL"] + E["E2E_DB_URL"]:
    raise RuntimeError("O teste ponta a ponta nunca roda contra o Supabase de produção.")

psycopg = pytest.importorskip("psycopg")
httpx = pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402
from supabase import create_client  # noqa: E402

import api.auth as auth_mod  # noqa: E402
from api.main import create_app as create_api  # noqa: E402
from config import load_settings  # noqa: E402
from instagram_service.app import create_app as create_ig  # noqa: E402
from instagram_service.config import InstagramConfig  # noqa: E402
from instagram_service.publisher import Publisher  # noqa: E402
from instagram_service.store import Database, Storage  # noqa: E402
from tests.test_instagram_service import TOKEN, FakeMeta  # noqa: E402


def login(email, password):
    c = create_client(E["E2E_SUPABASE_URL"], E["E2E_PUBLISHABLE_KEY"])
    s = c.auth.sign_in_with_password({"email": email, "password": password})
    return c, s.session.access_token


def sql(query, params=()):
    with psycopg.connect(E["E2E_DB_URL"], autocommit=True) as c:
        cur = c.execute(query, params)
        return cur.fetchall() if cur.description else None


@pytest.fixture(scope="module")
def env():
    settings = replace(load_settings(), db_backend="supabase", supabase_url=E["E2E_SUPABASE_URL"],
                       supabase_key=E["E2E_PUBLISHABLE_KEY"], store_slug="kika-cakes", public_app_url="https://vitrine.exemplo")
    auth_mod.load_settings = lambda: settings  # API e serviço validam o token no Supabase local
    sql("delete from public.instagram_publications")
    sql("delete from public.marketing_posts")
    sql("update public.instagram_accounts set status='desconectado', token_vault_id=null")
    sql("delete from vault.secrets where name like 'instagram_token_%%'")
    owner, token = login(E["E2E_OWNER_EMAIL"], E["E2E_OWNER_PASS"])
    meta = FakeMeta()
    cfg = InstagramConfig(app_id="123", app_secret="segredo", redirect_uri="https://servico.exemplo/v1/instagram/callback",
                          graph_version="v23.0", db_url=E["E2E_DB_URL"], supabase_url=E["E2E_SUPABASE_URL"],
                          service_key=E["E2E_SERVICE_KEY"])
    db = Database(E["E2E_DB_URL"])
    yield {
        "owner": owner, "token": token, "meta": meta, "db": db,
        "api": TestClient(create_api(), raise_server_exceptions=False),
        "ig": TestClient(create_ig(cfg=cfg, db=db, graph=meta.graph()), raise_server_exceptions=False),
        "publisher": Publisher(db, meta.graph(), Storage(E["E2E_SUPABASE_URL"], E["E2E_SERVICE_KEY"]), sleep=lambda s: None),
        "store": sql("select id from public.confeitarias where slug='kika-cakes'")[0][0],
    }


def bearer(env):
    return {"Authorization": f"Bearer {env['token']}"}


def test_1_oauth_connection_stores_token_encrypted_in_vault(env):
    r = env["ig"].get("/v1/instagram/conexao", headers=bearer(env))
    assert r.status_code == 200, r.text
    state = parse_qs(urlparse(r.json()["url"]).query)["state"][0]
    cb = env["ig"].get("/v1/instagram/callback", params={"code": "codigo", "state": state})
    assert cb.status_code == 200 and "conectado" in cb.text
    secret_id, raw = sql("""select s.id, s.secret from vault.secrets s join public.instagram_accounts a
                            on a.token_vault_id = s.id where a.confeitaria_id = %s""", (env["store"],))[0]
    assert raw != TOKEN  # cifrado de verdade no Vault do Supabase
    assert env["db"].token(str(env["store"]))[1] == TOKEN  # só o serviço lê decifrado
    acc = env["owner"].table("instagram_accounts").select("username,status").execute().data
    assert acc == [{"username": "kikacakes_confeitaria", "status": "conectado"}]
    with pytest.raises(Exception):
        env["owner"].table("instagram_accounts").select("token_vault_id").execute()


def test_2_studio_saves_real_png_and_schedule_is_idempotent(env):
    prod = env["owner"].table("produtos").select("id").eq("slug", "bem-casado").execute().data[0]["id"]
    body = {"produto_id": prod, "template": "produto", "formato": "feed", "tom": "amigavel", "usar_foto": False,
            "legenda": "Bem-casado da Kika! #kikacakes"}
    r = env["api"].post("/v1/marketing/posts", json=body, headers={**bearer(env), "Idempotency-Key": "e2e-post-0001"})
    assert r.status_code == 201, r.text
    again = env["api"].post("/v1/marketing/posts", json=body, headers={**bearer(env), "Idempotency-Key": "e2e-post-0001"})
    assert again.status_code == 200 and again.json()["id"] == r.json()["id"]
    post = r.json()["id"]
    png = env["api"].get(f"/v1/marketing/posts/{post}/imagem", headers=bearer(env))
    assert png.content.startswith(b"\x89PNG")
    args = {"p_post_id": post, "p_agendado_para": None, "p_idempotency_key": "e2e-agenda-0001"}
    a = env["owner"].rpc("agendar_publicacao_instagram", args).execute().data
    b = env["owner"].rpc("agendar_publicacao_instagram", args).execute().data
    assert a[0]["id"] == b[0]["id"] and a[0]["status"] == "agendado"
    env["post"], env["pub"] = post, a[0]["id"]
    blocked = env["api"].put(f"/v1/marketing/posts/{post}", json=body, headers=bearer(env))
    assert blocked.status_code == 409  # agendado: não edita


def test_3_publisher_converts_to_jpeg_signed_url_and_publishes(env):
    result = env["publisher"].run_once("e2e-worker")
    assert result["publicado"] == 1, result
    create = next(c for c in env["meta"].calls if c.url.path.endswith("/media") and c.method == "POST")
    image_url = parse_qs(create.content.decode())["image_url"][0]
    got = httpx.get(image_url, timeout=20)  # o link assinado do Storage funciona (é o que a Meta baixa)
    assert got.status_code == 200 and got.content[:3] == b"\xff\xd8\xff"  # JPEG
    assert httpx.get(image_url.split("?")[0].replace("/object/sign/", "/object/public/"), timeout=20).status_code >= 400
    pub = env["owner"].table("instagram_publications").select("status,ig_media_id,permalink,tentativas") \
        .eq("id", env["pub"]).execute().data[0]
    assert pub["status"] == "publicado" and pub["ig_media_id"] and pub["permalink"].startswith("https://www.instagram.com/")
    logs = [r["evento"] for r in env["owner"].table("instagram_publication_logs").select("evento,id")
            .eq("publication_id", env["pub"]).order("id").execute().data]
    assert logs == ["agendado", "container_criado", "publicacao_pedida", "publicado"]


def test_4_other_store_and_visitor_see_nothing(env):
    other, _ = login(E["E2E_OTHER_EMAIL"], E["E2E_OTHER_PASS"])
    assert other.table("instagram_publications").select("id").execute().data == []
    assert other.table("instagram_accounts").select("status").eq("confeitaria_id", str(env["store"])).execute().data == []
    with pytest.raises(Exception):
        other.rpc("agendar_publicacao_instagram", {"p_post_id": env["post"], "p_agendado_para": None,
                                                    "p_idempotency_key": "invasao-0001"}).execute()
    anon = create_client(E["E2E_SUPABASE_URL"], E["E2E_PUBLISHABLE_KEY"])
    with pytest.raises(Exception):
        anon.table("instagram_publications").select("id").execute()
    with pytest.raises(Exception):
        anon.rpc("instagram_token", {"p_conf": str(env["store"])}).execute()


def test_5_meta_failure_is_retried_then_reported(env):
    prod = env["owner"].table("produtos").select("id").eq("slug", "docinhos-tradicionais").execute().data[0]["id"]
    r = env["api"].post("/v1/marketing/posts", json={"produto_id": prod, "usar_foto": False, "formato": "story"},
                        headers={**bearer(env), "Idempotency-Key": "e2e-post-0002"})
    pub = env["owner"].rpc("agendar_publicacao_instagram", {"p_post_id": r.json()["id"], "p_agendado_para": None,
                                                            "p_idempotency_key": "e2e-agenda-0002"}).execute().data[0]
    env["meta"].create_error = {"message": "Service temporarily unavailable", "code": 2, "is_transient": True}
    env["publisher"].run_once("e2e-worker")
    row = env["owner"].table("instagram_publications").select("status,erro_mensagem").eq("id", pub["id"]).execute().data[0]
    assert row["status"] == "agendado" and "Nova tentativa" in row["erro_mensagem"]
    env["meta"].create_error = {"message": "Unsupported", "code": 9004, "error_subcode": 2207052}
    sql("update public.instagram_publications set proxima_tentativa_em = now() - interval '1 s' where id = %s", (pub["id"],))
    env["publisher"].run_once("e2e-worker")
    row = env["owner"].table("instagram_publications").select("status,ig_media_id").eq("id", pub["id"]).execute().data[0]
    assert row == {"status": "falhou", "ig_media_id": None}  # nada de "publicado" falso
    env["meta"].create_error = None


def test_6_disconnect_removes_token_from_vault(env):
    env["owner"].rpc("desconectar_instagram", {}).execute()
    assert env["db"].token(str(env["store"])) is None
    assert sql("select count(*) from vault.secrets where name = %s", (f"instagram_token_{env['store']}",))[0][0] == 0
