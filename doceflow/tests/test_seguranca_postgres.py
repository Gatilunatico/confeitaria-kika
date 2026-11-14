"""Etapa 2 (segurança): migrações 001–008 num PostgreSQL 16 real, com o ambiente Supabase emulado.

Cenário: duas confeitarias (Kika Cakes e "Outra Doceria"), a dona de cada uma, um usuário
logado SEM perfil administrativo e o visitante anônimo. Cada teste roda dentro de uma
transação desfeita no final (rollback), então os testes não interferem entre si.
"""

import json
import tempfile
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "database" / "migrations").glob("0*.sql"))
SEED = ROOT / "database" / "seed.sql"
SHIM = ROOT / "tests" / "sql" / "supabase_shim.sql"

OWNER_A, OWNER_B, NO_PROFILE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
DENIED = (psycopg.errors.InsufficientPrivilege,)
ORDER = "select * from public.criar_pedido(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
LEAD = "select * from public.criar_lead(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"


def order_args(slug="kika-cakes", phone="5511987650000", itens=None, **o):
    itens = itens if itens is not None else [{"produto_slug": "bem-casado", "quantidade": 50},
                                             {"produto_slug": "docinhos-tradicionais", "quantidade": 2}]
    d = dict(slug=slug, nome="Cliente Teste", fone=phone, data=date.today() + timedelta(days=10), modo="Entrega",
             obs="", itens=json.dumps(itens), origem="site", ok=True, endereco="Rua das Flores, 123, Centro, São Paulo")
    d.update(o)
    return tuple(d.values())


def lead_args(phone="5511987651111", prod="docinhos-tradicionais"):
    return ("kika-cakes", prod, "Ana Teste", phone, 2, date.today() + timedelta(days=7), "Retirada", "", "site", True)


@pytest.fixture(scope="module")
def pg():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="doceflow-sec-"), cleanup_mode="stop")
    with psycopg.connect(server.get_uri(), autocommit=True) as c:
        c.execute(SHIM.read_text(encoding="utf-8"))
        for _ in range(2):  # idempotência: todas as migrações rodam duas vezes sem erro
            for m in MIGRATIONS:
                c.execute(m.read_text(encoding="utf-8"))
        c.execute(SEED.read_text(encoding="utf-8"))
        c.execute("insert into auth.users (id, email) values (%s,'dona.a@teste.dev'),(%s,'dona.b@teste.dev'),"
                  "(%s,'sem.perfil@teste.dev')", (OWNER_A, OWNER_B, NO_PROFILE))
        c.execute("insert into public.confeitarias (slug, nome) values ('outra', 'Outra Doceria')")
        c.execute("""insert into public.produtos (confeitaria_id, slug, nome, categoria, unidade, preco, tipo_preco)
                     select id, 'bolo-b', 'Bolo da B', 'Bolos', 'kg', 80, 'a_partir_de'
                       from public.confeitarias where slug = 'outra'""")
        # procedimento oficial do primeiro administrador (papel postgres, no SQL Editor)
        c.execute("select public.cadastrar_admin('dona.a@teste.dev', 'kika-cakes')")
        c.execute("select public.cadastrar_admin('dona.b@teste.dev', 'outra')")
        # dados privados de cada loja, criados pelos fluxos públicos
        c.execute("set role anon")
        c.execute(ORDER, order_args(phone="5511987650001"))
        c.execute(ORDER, order_args(slug="outra", phone="5511987650002",
                                    itens=[{"produto_slug": "bolo-b", "quantidade": 2}]))
        c.execute(LEAD, lead_args())
        c.execute("reset role")
    yield server
    server.cleanup()


@pytest.fixture
def db(pg):
    """Conexão com transação desfeita no final de cada teste."""
    with psycopg.connect(pg.get_uri()) as conn:
        yield conn
        conn.rollback()


def ids(db):
    db.execute("reset role")
    a = db.execute("select id from public.confeitarias where slug='kika-cakes'").fetchone()[0]
    b = db.execute("select id from public.confeitarias where slug='outra'").fetchone()[0]
    return a, b


def as_role(db, role, user=None):
    db.execute("reset role")
    db.execute("select set_config('request.jwt.claim.sub', %s, true)", (str(user) if user else "",))
    db.execute(f"set local role {role}")


def denied(db, sql, params=()):
    db.execute("savepoint s")
    try:
        cur = db.execute(sql, params)
    except DENIED:
        db.execute("rollback to savepoint s")
        return True
    rows = cur.rowcount
    db.execute("rollback to savepoint s")
    return rows == 0  # RLS filtrou: nenhuma linha afetada/lida


def raises(db, sql, params, match):
    db.execute("savepoint s")
    with pytest.raises(psycopg.Error, match=match):
        db.execute(sql, params)
    db.execute("rollback to savepoint s")


# ================================================================ visitante
@pytest.mark.parametrize("table", ["leads", "orders", "order_items", "admin_profiles", "marketing_posts",
                                   "instagram_accounts", "leads_antiga"])
def test_visitor_cannot_read_private_tables(db, table):
    exists = db.execute("select to_regclass(%s)", (f"public.{table}",)).fetchone()[0]
    if exists is None:
        pytest.skip(f"{table} não existe neste banco")
    as_role(db, "anon")
    assert denied(db, f"select * from public.{table}")


def test_visitor_reads_only_published_catalog(db):
    a, _ = ids(db)
    db.execute("update public.produtos set publicado = false where slug = 'kit-inexistente' or slug = 'cupcake-tag'")
    as_role(db, "anon")
    slugs = {r[0] for r in db.execute("select slug from public.produtos")}
    assert "cupcake-tag" not in slugs and "bem-casado" in slugs and "bolo-b" in slugs


@pytest.mark.parametrize("sql", [
    "insert into public.produtos (confeitaria_id, slug, nome, categoria, unidade, tipo_preco) "
    "select id, 'x-anon', 'X', 'Bolos', 'kg', 'sob_consulta' from public.confeitarias limit 1",
    "update public.produtos set preco = 1",
    "update public.leads set status = 'Perdido'",
    "update public.orders set status = 'Cancelado'",
    "delete from public.orders",
    "insert into public.admin_profiles (user_id, confeitaria_id) select gen_random_uuid(), id from public.confeitarias",
    "update public.confeitarias set whatsapp = '5511900000000'",
    "select public.cadastrar_admin('dona.a@teste.dev', 'kika-cakes')",
])
def test_unauthenticated_cannot_run_admin_operations(db, sql):
    as_role(db, "anon")
    assert denied(db, sql)


def test_public_order_flow_works_and_returns_only_own_order(db):
    as_role(db, "anon")
    row = db.execute(ORDER, order_args(phone="5511987650100")).fetchone()
    _id, protocolo, criado, status, valor, nome_loja, _ = row
    assert criado and status == "Aguardando confirmação" and protocolo.startswith("PD-") and nome_loja == "Kika Cakes"
    assert float(valor) == 50 * 6.0 + 2 * 150.0  # estimativa "a partir de"
    again = db.execute(ORDER, order_args(phone="5511987650100")).fetchone()
    assert again[1] == protocolo and again[2] is False  # repetido: não duplica


@pytest.mark.parametrize("override,code", [
    ({"slug": "nao-existe"}, "confeitaria_invalida"),
    ({"itens": [{"produto_slug": "bolo-b", "quantidade": 2}]}, "produto_invalido"),  # produto de OUTRA loja
    ({"itens": [{"produto_slug": "bem-casado", "quantidade": 10}]}, "quantidade_invalida"),  # mínimo 25
    ({"itens": [{"produto_slug": "bem-casado", "quantidade": "50"}]}, "quantidade_invalida"),
    ({"itens": []}, "itens_invalidos"),
    ({"itens": [{"produto_slug": "bem-casado", "quantidade": 50}] * 2}, "itens_repetidos"),
    ({"itens": [{"produto_slug": "bem-casado", "quantidade": 30}] * 21}, "itens_invalidos"),
    ({"data": date.today() - timedelta(days=1)}, "data_invalida"),
    ({"ok": False}, "consentimento_obrigatorio"),
    ({"fone": "123"}, "orders_cliente_whatsapp_check"),
    ({"modo": "Drone"}, "modalidade_invalida"),
    ({"endereco": "  "}, "endereco_obrigatorio"),     # entrega sem endereço
    ({"endereco": "x" * 301}, "endereco_invalido"),
])
def test_public_order_validation(db, override, code):
    as_role(db, "anon")
    args = dict(zip(["slug", "nome", "fone", "data", "modo", "obs", "itens", "origem", "ok", "endereco"],
                    order_args(phone="5511987650200")))
    if "itens" in override:
        override = {**override, "itens": json.dumps(override["itens"])}
    args.update(override)
    raises(db, ORDER, tuple(args.values()), code)


def test_unpublished_product_cannot_be_ordered_or_quoted(db):
    db.execute("update public.produtos set publicado = false where slug = 'bem-casado'")
    as_role(db, "anon")
    raises(db, ORDER, order_args(phone="5511987650300"), "produto_invalido")
    raises(db, LEAD, lead_args(prod="bem-casado"), "produto_invalido")


def test_rate_limit_per_whatsapp(db):
    as_role(db, "anon")
    for i in range(5):
        db.execute(ORDER, order_args(phone="5511987650400",
                                     itens=[{"produto_slug": "docinhos-tradicionais", "quantidade": i + 1}]))
    raises(db, ORDER, order_args(phone="5511987650400",
                                 itens=[{"produto_slug": "docinhos-tradicionais", "quantidade": 9}]), "limite_excedido")
    raises(db, LEAD, lead_args(phone="5511987650400"), "limite_excedido")


# ================================================================ proprietária
def test_owner_sees_own_products_including_unpublished(db):
    a, _ = ids(db)
    db.execute("update public.produtos set publicado = false where slug = 'cupcake-tag'")
    as_role(db, "authenticated", OWNER_A)
    rows = db.execute("select slug, confeitaria_id from public.produtos where confeitaria_id = %s", (a,)).fetchall()
    assert "cupcake-tag" in {r[0] for r in rows} and len(rows) == 27


def test_owner_creates_and_edits_products(db):
    a, _ = ids(db)
    as_role(db, "authenticated", OWNER_A)
    db.execute("""insert into public.produtos (confeitaria_id, slug, nome, categoria, unidade, preco, tipo_preco)
                  values (%s, 'torta-nova', 'Torta Nova', 'Tortas', 'unidade', 60, 'a_partir_de')""", (a,))
    db.execute("update public.produtos set preco = 65, publicado = false where slug = 'torta-nova'")
    assert db.execute("select preco, publicado from public.produtos where slug='torta-nova'").fetchone() == (65, False)


def test_owner_reads_and_updates_own_orders(db):
    a, _ = ids(db)
    as_role(db, "authenticated", OWNER_A)
    rows = db.execute("select confeitaria_id, status from public.orders").fetchall()
    assert rows and {r[0] for r in rows} == {a}
    assert db.execute("select count(*) from public.order_items").fetchone()[0] >= 2
    db.execute("update public.orders set status = 'Confirmado', valor_final = 420")
    assert db.execute("select status_atualizado_em is not null from public.orders limit 1").fetchone()[0]
    assert denied(db, "update public.orders set cliente_whatsapp = '5511900000000'")  # coluna não editável


def test_owner_reads_own_leads_and_updates_store_contact(db):
    a, _ = ids(db)
    as_role(db, "authenticated", OWNER_A)
    assert {r[0] for r in db.execute("select confeitaria_id from public.leads")} == {a}
    db.execute("update public.confeitarias set whatsapp = '5511979855065' where id = %s", (a,))
    assert denied(db, "update public.confeitarias set slug = 'outro-slug'")  # slug não é editável


# ================================================================ isolamento entre confeitarias
@pytest.mark.parametrize("table", ["orders", "order_items", "leads"])
def test_other_store_admin_cannot_read_records(db, table):
    a, _ = ids(db)
    as_role(db, "authenticated", OWNER_B)
    assert db.execute(f"select count(*) from public.{table} where confeitaria_id = %s", (a,)).fetchone()[0] == 0


@pytest.mark.parametrize("sql", [
    "update public.orders set status = 'Cancelado' where confeitaria_id = %s",
    "update public.leads set status = 'Perdido' where confeitaria_id = %s",
    "update public.produtos set preco = 1 where confeitaria_id = %s",
    "update public.confeitarias set nome = 'Invadida' where id = %s",
])
def test_other_store_admin_cannot_modify_records(db, sql):
    a, _ = ids(db)
    as_role(db, "authenticated", OWNER_B)
    assert denied(db, sql, (a,))


def test_other_store_admin_cannot_insert_into_other_store(db):
    a, _ = ids(db)
    as_role(db, "authenticated", OWNER_B)
    db.execute("savepoint s")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        db.execute("""insert into public.produtos (confeitaria_id, slug, nome, categoria, unidade, tipo_preco)
                      values (%s, 'invasao', 'Invasão', 'Bolos', 'kg', 'sob_consulta')""", (a,))
    db.execute("rollback to savepoint s")


def test_logged_user_without_profile_has_no_admin_access(db):
    as_role(db, "authenticated", NO_PROFILE)
    for table in ("orders", "leads", "order_items"):
        assert db.execute(f"select count(*) from public.{table}").fetchone()[0] == 0
    assert denied(db, "update public.produtos set preco = 1")


# ================================================================ papel e vínculo
@pytest.mark.parametrize("sql", [
    "update public.admin_profiles set papel = 'proprietaria'",
    "update public.admin_profiles set confeitaria_id = (select id from public.confeitarias where slug='outra')",
    "insert into public.admin_profiles (user_id, confeitaria_id) "
    "select auth.uid(), id from public.confeitarias where slug = 'outra'",
    "delete from public.admin_profiles",
    "select public.cadastrar_admin('sem.perfil@teste.dev', 'kika-cakes')",
    "update public.confeitarias set owner_user_id = auth.uid()",
])
def test_user_cannot_change_own_role_or_store(db, sql):
    as_role(db, "authenticated", OWNER_B)
    assert denied(db, sql)


def test_admin_reads_only_own_profile(db):
    as_role(db, "authenticated", OWNER_A)
    rows = db.execute("select user_id from public.admin_profiles").fetchall()
    assert [r[0] for r in rows] == [OWNER_A]


def test_inactive_profile_loses_access(db):
    db.execute("update public.admin_profiles set ativo = false where user_id = %s", (OWNER_A,))
    as_role(db, "authenticated", OWNER_A)
    assert db.execute("select count(*) from public.orders").fetchone()[0] == 0


def test_bootstrap_admin_rules(db):
    raises(db, "select public.cadastrar_admin(%s, %s)", ("dona.a@teste.dev", "outra"),
           "usuario_ja_administra_outra_confeitaria")
    raises(db, "select public.cadastrar_admin(%s, %s)", ("ninguem@teste.dev", "kika-cakes"), "usuario_nao_encontrado")


# ================================================================ consistência multi-tenant
def test_items_cannot_mix_stores(db):
    a, b = ids(db)
    order_a = db.execute("select id from public.orders where confeitaria_id = %s limit 1", (a,)).fetchone()[0]
    prod_b = db.execute("select id from public.produtos where slug = 'bolo-b'").fetchone()[0]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        db.execute("""insert into public.order_items (order_id, confeitaria_id, produto_id, produto_nome, unidade,
                      quantidade, tipo_preco) values (%s, %s, %s, 'x', 'kg', 1, 'a_partir_de')""", (order_a, a, prod_b))


# ================================================================ Storage
def _obj(db, bucket, name):
    db.execute("savepoint s")
    try:
        db.execute("insert into storage.objects (bucket_id, name) values (%s, %s)", (bucket, name))
        db.execute("release savepoint s")
        return True
    except psycopg.Error:
        db.execute("rollback to savepoint s")
        return False


def test_buckets_configuration(db):
    rows = {r[0]: r[1:] for r in db.execute("select id, public, file_size_limit from storage.buckets")}
    assert rows["marketing"] == (False, 5242880)       # privado
    assert rows["product-images"] == (True, 5242880)   # leitura pública


def test_private_marketing_files_are_protected(db):
    a, _ = ids(db)
    path = f"{a}/{uuid.uuid4()}.png"
    as_role(db, "authenticated", OWNER_A)
    assert _obj(db, "marketing", path)
    as_role(db, "anon")
    assert db.execute("select count(*) from storage.objects where bucket_id='marketing'").fetchone()[0] == 0
    assert not _obj(db, "marketing", f"{a}/{uuid.uuid4()}.png")
    as_role(db, "authenticated", OWNER_B)
    assert db.execute("select count(*) from storage.objects where bucket_id='marketing'").fetchone()[0] == 0
    assert not _obj(db, "marketing", f"{a}/{uuid.uuid4()}.png")
    assert denied(db, "delete from storage.objects where bucket_id = 'marketing'")


def test_product_photos_only_admin_writes_own_folder(db):
    a, b = ids(db)
    prod_a = db.execute("select id from public.produtos where slug='bem-casado'").fetchone()[0]
    path = f"{a}/{prod_a}/{uuid.uuid4()}.jpg"
    as_role(db, "anon")
    assert not _obj(db, "product-images", path)
    as_role(db, "authenticated", OWNER_B)
    assert not _obj(db, "product-images", path)            # pasta de outra loja
    as_role(db, "authenticated", OWNER_A)
    assert _obj(db, "product-images", path)
    db.execute("insert into public.product_images (confeitaria_id, produto_id, storage_path, principal) "
               "values (%s, %s, %s, true)", (a, prod_a, path))
    as_role(db, "anon")
    assert db.execute("select count(*) from public.product_images").fetchone()[0] == 1  # foto pública do produto


def test_product_image_path_must_match_store_and_product(db):
    a, b = ids(db)
    prod_a = db.execute("select id from public.produtos where slug='bem-casado'").fetchone()[0]
    as_role(db, "authenticated", OWNER_A)
    db.execute("savepoint s")
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute("insert into public.product_images (confeitaria_id, produto_id, storage_path) values (%s,%s,%s)",
                   (a, prod_a, f"{b}/{prod_a}/{uuid.uuid4()}.jpg"))
    db.execute("rollback to savepoint s")


def test_instagram_token_reference_is_not_readable(db):
    a, _ = ids(db)
    as_role(db, "authenticated", OWNER_A)
    db.execute("insert into public.instagram_accounts (confeitaria_id, username) values (%s, 'kikacakes_confeitaria')",
               (a,))
    assert db.execute("select username, status from public.instagram_accounts").fetchone() == \
        ("kikacakes_confeitaria", "desconectado")
    assert denied(db, "select token_vault_id from public.instagram_accounts")
    assert denied(db, "update public.instagram_accounts set token_vault_id = gen_random_uuid()")
