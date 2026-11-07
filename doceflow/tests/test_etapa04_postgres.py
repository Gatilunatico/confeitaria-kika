"""Etapa 04: migração 002 num PostgreSQL 16 real (pgserver), com RLS do painel."""

import tempfile
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parents[1]
M1 = ROOT / "supabase" / "migrations" / "001_schema_leads.sql"
M2 = ROOT / "supabase" / "migrations" / "002_painel_admin.sql"
SEED = ROOT / "supabase" / "seed.sql"
SHIM = ROOT / "tests" / "sql" / "supabase_shim.sql"
OWNER, INTRUDER = uuid.uuid4(), uuid.uuid4()
CALL = "select protocolo from public.criar_lead(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"


def lead_args(phone):
    return ("kika-cakes", "docinhos-tradicionais", "Ana Teste", phone, 2, date.today() + timedelta(days=7),
            "Retirada", "", "site", True)


@pytest.fixture(scope="module")
def pg():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="doceflow-pg4-"), cleanup_mode="stop")
    with psycopg.connect(server.get_uri(), autocommit=True) as c:
        c.execute(SHIM.read_text(encoding="utf-8"))
        c.execute(M1.read_text(encoding="utf-8"))
        c.execute(SEED.read_text(encoding="utf-8"))
        c.execute("insert into auth.users (id) values (%s), (%s)", (OWNER, INTRUDER))
        c.execute("update public.confeitarias set owner_user_id = %s", (OWNER,))
        c.execute("insert into public.confeitarias (slug, nome, owner_user_id) values ('outra', 'Outra', %s)",
                  (INTRUDER,))
        # leads criados ANTES da 002, com status antigos
        p1 = c.execute(CALL, lead_args("5511987650101")).fetchone()[0]
        p2 = c.execute(CALL, lead_args("5511987650102")).fetchone()[0]
        c.execute("update public.leads set status = 'Em contato' where protocolo = %s", (p1,))
        c.execute("update public.leads set status = 'Fechado' where protocolo = %s", (p2,))
        c.execute(M2.read_text(encoding="utf-8"))
        c.execute(M2.read_text(encoding="utf-8"))  # idempotente
    server.old_protocols = (p1, p2)
    yield server
    server.cleanup()


@pytest.fixture
def conn(pg):
    with psycopg.connect(pg.get_uri(), autocommit=True) as c:
        yield c


def as_role(c, role, user=None):
    c.execute("reset role")
    c.execute("select set_config('request.jwt.claim.sub', %s, false)", (str(user) if user else "",))
    c.execute(f"set role {role}")


def test_old_statuses_were_mapped(pg, conn):
    p1, p2 = pg.old_protocols
    rows = dict(conn.execute("select protocolo, status from public.leads where protocolo in (%s, %s)", (p1, p2)))
    assert rows == {p1: "Em atendimento", p2: "Venda concluída"}


@pytest.mark.parametrize("status", ["Novo", "Em atendimento", "Orçamento enviado", "Venda concluída", "Perdido"])
def test_owner_can_set_every_new_status(conn, status):
    as_role(conn, "anon")
    proto = conn.execute(CALL, lead_args("5511987650200")).fetchone()[0]
    as_role(conn, "authenticated", OWNER)
    conn.execute("update public.leads set status = %s where protocolo = %s", (status, proto))
    assert conn.execute("select status from public.leads where protocolo = %s", (proto,)).fetchone()[0] == status


def test_old_or_invalid_status_rejected(conn):
    as_role(conn, "authenticated", OWNER)
    for bad in ("Fechado", "Em contato", "Vendido"):
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("update public.leads set status = %s", (bad,))


def test_status_change_timestamp(conn):
    as_role(conn, "anon")
    proto = conn.execute(CALL, lead_args("5511987650300")).fetchone()[0]
    as_role(conn, "authenticated", OWNER)
    assert conn.execute("select status_atualizado_em from public.leads where protocolo=%s", (proto,)).fetchone()[0] \
        is None
    conn.execute("update public.leads set status = 'Perdido' where protocolo = %s", (proto,))
    assert conn.execute("select status_atualizado_em from public.leads where protocolo=%s", (proto,)).fetchone()[0]


def _kika_id(conn):
    conn.execute("reset role")
    return conn.execute("select id from public.confeitarias where slug='kika-cakes'").fetchone()[0]


def test_owner_creates_and_edits_own_products(conn):
    kika = _kika_id(conn)
    as_role(conn, "authenticated", OWNER)
    conn.execute("""insert into public.produtos (confeitaria_id, slug, nome, categoria, unidade, preco, tipo_preco)
                    values (%s, 'torta-limao', 'Torta de limão', 'Tortas', 'unidade', 60, 'a_partir_de')""", (kika,))
    conn.execute("update public.produtos set preco = 72.5, disponivel = false where slug = 'torta-limao'")
    row = conn.execute("select preco, disponivel from public.produtos where slug='torta-limao'").fetchone()
    assert float(row[0]) == 72.5 and row[1] is False


def test_owner_cannot_change_slug_or_store(conn):
    as_role(conn, "authenticated", OWNER)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("update public.produtos set slug = 'outro' where slug = 'docinhos-tradicionais'")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("update public.produtos set confeitaria_id = gen_random_uuid() where slug = 'docinhos-tradicionais'")


def test_intruder_cannot_write_other_store_products(conn):
    kika = _kika_id(conn)
    as_role(conn, "authenticated", INTRUDER)
    conn.execute("update public.produtos set preco = 1 where slug = 'docinhos-tradicionais'")  # RLS: 0 linhas
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("""insert into public.produtos (confeitaria_id, slug, nome, categoria, unidade, tipo_preco)
                        values (%s, 'invasao', 'Invasão', 'X', 'un', 'sob_consulta')""", (kika,))
    as_role(conn, "authenticated", OWNER)
    assert float(conn.execute("select preco from public.produtos where slug='docinhos-tradicionais' and confeitaria_id=%s",
                              (kika,)).fetchone()[0]) != 1


def test_intruder_sees_no_leads_and_cannot_update(conn):
    as_role(conn, "authenticated", INTRUDER)
    assert conn.execute("select count(*) from public.leads").fetchone()[0] == 0
    conn.execute("update public.leads set status = 'Perdido'")
    as_role(conn, "authenticated", OWNER)
    assert conn.execute("select count(*) from public.leads where status = 'Perdido'").fetchone()[0] <= 2


def test_anon_cannot_write_products(conn):
    as_role(conn, "anon")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("update public.produtos set preco = 0")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("""insert into public.produtos (confeitaria_id, slug, nome, categoria, unidade, tipo_preco)
                        select id, 'x1', 'X1', 'X', 'un', 'sob_consulta' from public.confeitarias limit 1""")
