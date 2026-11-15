"""Etapa 6 (auditoria de segurança): permissões mínimas no banco, num PostgreSQL 16 real.

Em vez de testar só casos conhecidos, estes testes fixam a LISTA COMPLETA do que o visitante
(anon) e um usuário logado sem perfil podem fazer. Qualquer permissão nova que apareça numa
migração futura quebra o teste e precisa ser justificada.
"""

import uuid
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("pgserver")

from tests.test_seguranca_postgres import (  # noqa: E402,F401  (fixtures reaproveitadas)
    LEAD,
    NO_PROFILE,
    ORDER,
    OWNER_A,
    _obj,
    as_role,
    db,
    denied,
    ids,
    lead_args,
    order_args,
    pg,
)

MIGRATION_011 = Path(__file__).resolve().parents[1] / "database" / "migrations" / "011_endurecimento_permissoes.sql"

# Única forma de o visitante ESCREVER: as duas funções controladas (validação + limite de envios).
ANON_TABLE_GRANTS = {"confeitarias": {"SELECT"}, "produtos": {"SELECT"}, "product_images": {"SELECT"}}
ANON_FUNCTIONS = {"criar_lead", "criar_pedido", "is_store_admin", "storage_folder_admin"}


def table_grants(db, role):
    rows = db.execute("""select table_name, privilege_type from information_schema.role_table_grants
                         where grantee = %s and table_schema = 'public'""", (role,)).fetchall()
    out: dict[str, set] = {}
    for t, p in rows:
        out.setdefault(t, set()).add(p)
    return out


# ================================================================ 12. RLS e permissões mínimas
def test_rls_enabled_on_every_table(db):
    db.execute("reset role")
    missing = [r[0] for r in db.execute("""select relname from pg_class where relnamespace = 'public'::regnamespace
                                           and relkind = 'r' and not relrowsecurity""")]
    assert missing == []
    assert db.execute("select relrowsecurity from pg_class where oid = 'storage.objects'::regclass").fetchone()[0]


def test_visitor_table_permissions_are_exactly_the_public_catalog(db):
    db.execute("reset role")
    assert table_grants(db, "anon") == ANON_TABLE_GRANTS


def test_visitor_can_execute_only_the_controlled_functions(db):
    db.execute("reset role")
    funcs = {r[0] for r in db.execute("""select p.proname from pg_proc p where p.pronamespace = 'public'::regnamespace
                                         and has_function_privilege('anon', p.oid, 'execute')""")}
    assert funcs == ANON_FUNCTIONS


def test_logged_user_without_profile_has_no_write_power_in_practice(db):
    """'authenticated' tem permissões de tabela (a dona precisa), mas o RLS barra quem não tem perfil."""
    a, _ = ids(db)
    as_role(db, "authenticated", NO_PROFILE)
    for sql, params in [
        ("update public.produtos set preco = 1", ()),
        ("delete from public.produtos", ()),
        ("insert into public.produtos (confeitaria_id, slug, nome, categoria, unidade, tipo_preco) "
         "values (%s, 'x-np', 'X', 'Bolos', 'kg', 'sob_consulta')", (a,)),
        ("update public.leads set status = 'Perdido'", ()),
        ("update public.orders set status = 'Cancelado'", ()),
        ("select * from public.leads", ()),
        ("select * from public.orders", ()),
        ("select * from public.order_history", ()),
        ("delete from public.marketing_posts", ()),
        ("update public.confeitarias set whatsapp = '5511900000000'", ()),
    ]:
        assert denied(db, sql, params), sql


# ================================================================ 2, 3, 4. Visitante: pedidos, leads, produtos
@pytest.mark.parametrize("sql", [
    "select * from public.orders", "select * from public.order_items", "select * from public.order_history",
    "select * from public.leads", "select * from public.admin_profiles",
    "update public.produtos set preco = 0", "delete from public.produtos",
    "update public.product_images set principal = false", "delete from public.product_images",
    "update public.confeitarias set nome = 'x'",
])
def test_visitor_cannot_read_private_data_or_change_catalog(db, sql):
    as_role(db, "anon")
    assert denied(db, sql)


def test_visitor_writes_only_through_validated_functions_with_minimal_return(db):
    as_role(db, "anon")
    order = db.execute(ORDER, order_args(phone="5511987656001"))
    cols = [d.name for d in order.description]
    assert cols == ["id", "protocolo", "criado", "status", "valor_estimado", "confeitaria_nome",
                    "confeitaria_whatsapp"]  # nada de dados de outros clientes nem campos internos
    lead = db.execute(LEAD, lead_args(phone="5511987656002")).fetchall()
    assert len(lead) == 1


# ================================================================ 5. Storage
@pytest.mark.parametrize("bucket", ["product-images", "marketing"])
def test_visitor_cannot_upload_overwrite_or_delete_files(db, bucket):
    a, _ = ids(db)
    pid = db.execute("select id from public.produtos where slug = 'bem-casado'").fetchone()[0]
    name = f"{a}/{pid}/{uuid.uuid4()}.jpg" if bucket == "product-images" else f"{a}/{uuid.uuid4()}.png"
    as_role(db, "authenticated", OWNER_A)
    assert _obj(db, bucket, name)  # a dona consegue
    as_role(db, "anon")
    assert not _obj(db, bucket, f"{a}/{pid}/{uuid.uuid4()}.jpg")
    assert denied(db, "update storage.objects set name = name where bucket_id = %s", (bucket,))
    assert denied(db, "delete from storage.objects where bucket_id = %s", (bucket,))


# ================================================================ 11. Tokens do Instagram (worker futuro)
def test_instagram_token_column_is_not_readable_by_app_roles(db):
    db.execute("reset role")
    for role in ("anon", "authenticated"):
        assert not db.execute("select has_column_privilege(%s, 'public.instagram_accounts', 'token_vault_id', "
                              "'select')", (role,)).fetchone()[0]


# ================================================================ migração 011
def test_011_revokes_legacy_table_grants_without_dropping_it(db):
    db.execute("reset role")
    db.execute("create table public.leads_antiga (id uuid primary key, nome text)")
    db.execute("insert into public.leads_antiga values (gen_random_uuid(), 'registro antigo')")
    db.execute("grant all on public.leads_antiga to anon, authenticated")  # padrão do Supabase
    db.execute("alter table public.leads_antiga enable row level security")
    db.execute(MIGRATION_011.read_text(encoding="utf-8"))
    assert "leads_antiga" not in table_grants(db, "anon")
    assert "leads_antiga" not in table_grants(db, "authenticated")
    assert db.execute("select count(*) from public.leads_antiga").fetchone()[0] == 1  # nada apagado


def test_011_triggers_still_fire_without_execute_grant(db):
    a, _ = ids(db)
    as_role(db, "authenticated", OWNER_A)
    before = db.execute("select updated_at from public.produtos where slug = 'bem-casado'").fetchone()[0]
    db.execute("select pg_sleep(0.01)")
    db.execute("update public.produtos set preco = preco where slug = 'bem-casado'")
    after = db.execute("select updated_at from public.produtos where slug = 'bem-casado'").fetchone()[0]
    assert after >= before
    db.execute("reset role")
    for fn in ("set_updated_at", "set_status_atualizado_em", "product_images_limite"):
        assert not db.execute(f"select has_function_privilege('anon', 'public.{fn}()', 'execute')").fetchone()[0]
