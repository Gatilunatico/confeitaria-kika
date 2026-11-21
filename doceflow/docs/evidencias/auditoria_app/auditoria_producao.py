"""Auditoria SOMENTE LEITURA do Supabase de produção (Etapa: auditoria antes da distribuição).

- Banco: uma transação `read only` (nada é gravado; no pooler de transações, sem SET de sessão).
- API pública: só a chave publishable, como um visitante ou um APK sem login.
Não imprime chaves, senhas nem dados de clientes (só contagens e nomes de objetos).
Uso: python docs/evidencias/auditoria_app/auditoria_producao.py   (de dentro de doceflow/, com o .env)
"""

import json
import sys
from pathlib import Path

import httpx
import psycopg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[3]
env = dotenv_values(ROOT / ".env")
DB, URL, KEY = env["SUPABASE_DB_URL"], env["SUPABASE_URL"].rstrip("/"), env["SUPABASE_KEY"]
out: dict = {}


def section(name, value):
    out[name] = value
    print(f"\n## {name}\n{json.dumps(value, ensure_ascii=False, indent=1, default=str)}")


with psycopg.connect(DB, autocommit=False, prepare_threshold=None) as c:
    with c.transaction():
        c.execute("set transaction read only")
        q = lambda s, p=(): c.execute(s, p).fetchall()  # noqa: E731
        section("migracoes_presentes", {
            "012_painel_indicadores": q("select to_regprocedure('public.painel_indicadores(date,date)') is not null")[0][0],
            "013_admin_devices": q("select to_regclass('public.admin_devices') is not null")[0][0],
            "014_instagram_publications": q("select to_regclass('public.instagram_publications') is not null")[0][0],
        })
        section("tabelas_public_sem_rls", [r[0] for r in q(
            "select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='public' and c.relkind='r' and not c.relrowsecurity order by 1")])
        section("privilegios_de_tabela_para_anon", [list(r) for r in q(
            "select table_name, string_agg(privilege_type, ',' order by privilege_type) from information_schema.role_table_grants "
            "where grantee='anon' and table_schema='public' group by 1 order by 1")])
        section("privilegios_de_coluna_para_anon", [list(r) for r in q(
            "select table_name, privilege_type, count(*) from information_schema.column_privileges "
            "where grantee='anon' and table_schema='public' and privilege_type <> 'SELECT' group by 1,2 order by 1")])
        section("funcoes_executaveis_por_anon", [list(r) for r in q(
            "select p.proname, p.prosecdef from pg_proc p join pg_namespace n on n.oid=p.pronamespace "
            "where n.nspname='public' and has_function_privilege('anon', p.oid, 'execute') order by 1")])
        section("views_public", [list(r) for r in q(
            "select c.relname, coalesce(array_to_string(c.reloptions, ','), '') , has_table_privilege('anon', c.oid, 'select') "
            "from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='v' order by 1")])
        section("buckets", [list(r) for r in q(
            "select id, public, file_size_limit, allowed_mime_types from storage.buckets order by 1")])
        section("politicas_storage_para_anon_ou_public", [list(r) for r in q(
            "select policyname, cmd, roles::text from pg_policies where schemaname='storage' and tablename='objects' "
            "and (roles::text like '%%anon%%' or roles::text like '%%public%%') order by 1")])
        section("contagens", dict(zip(["produtos", "publicados", "fotos", "leads", "orders", "perfis_admin", "usuarios_auth"], q(
            "select (select count(*) from public.produtos), (select count(*) from public.produtos where publicado), "
            "(select count(*) from public.product_images), (select count(*) from public.leads), (select count(*) from public.orders), "
            "(select count(*) from public.admin_profiles where ativo), (select count(*) from auth.users)")[0])))

h = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
http = httpx.Client(timeout=20)
section("auth_settings_publico", {k: v for k, v in http.get(f"{URL}/auth/v1/settings", headers={"apikey": KEY}).json().items()
                                  if k in ("disable_signup", "mailer_autoconfirm", "phone_autoconfirm", "sms_provider")})
rest = {}
for t in ["leads", "orders", "order_items", "order_history", "admin_profiles", "marketing_posts", "instagram_accounts",
          "clientes_resumo", "admin_devices", "instagram_publications", "leads_antiga", "confeitarias", "produtos",
          "product_images"]:
    r = http.get(f"{URL}/rest/v1/{t}?select=*&limit=1", headers=h)
    rest[t] = f"HTTP {r.status_code}" + (f", {len(r.json())} linha(s)" if r.status_code == 200 else "")
section("visitante_le_tabelas", rest)
rpc = {}
for fn, body in [("painel_indicadores", {}), ("converter_orcamento_em_pedido", {"p_lead_id": "00000000-0000-0000-0000-000000000000"}),
                 ("registrar_dispositivo", {"p_token": "x" * 30}), ("cadastrar_admin", {"p_email": "a@b.c", "p_confeitaria_slug": "kika-cakes"}),
                 ("definir_foto_principal", {"p_image_id": "00000000-0000-0000-0000-000000000000"})]:
    r = http.post(f"{URL}/rest/v1/rpc/{fn}", headers=h, json=body)
    rpc[fn] = f"HTTP {r.status_code}"
section("visitante_chama_funcoes", rpc)
st = {}
for b in ["marketing", "product-images", "instagram-media"]:
    r = http.post(f"{URL}/storage/v1/object/list/{b}", headers=h, json={"prefix": "", "limit": 5})
    st[f"listar {b}"] = f"HTTP {r.status_code}" + (f", {len(r.json())} item(ns)" if r.status_code == 200 else "")
    up = http.post(f"{URL}/storage/v1/object/{b}/auditoria/teste.png", headers={**h, "content-type": "image/png"}, content=b"x")
    st[f"enviar {b}"] = f"HTTP {up.status_code}"
section("visitante_storage", st)
(Path(__file__).with_name("resultado_producao.json")).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str),
                                                                 encoding="utf-8")
sys.exit(0)
