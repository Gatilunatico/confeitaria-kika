"""Etapa 03: migração Supabase executada num PostgreSQL 16 real (pgserver).

Valida schema, RLS e a função criar_lead com os papéis anon/authenticated,
emulando auth.uid() como o Supabase faz. Pulado se pgserver/psycopg não
estiverem instalados (requirements-dev.txt).
"""

import tempfile
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase" / "migrations" / "001_schema_leads.sql"
SEED = ROOT / "supabase" / "seed.sql"
SHIM = ROOT / "tests" / "sql" / "supabase_shim.sql"
OWNER = uuid.uuid4()
INTRUDER = uuid.uuid4()
CALL = "select * from public.criar_lead(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"


@pytest.fixture(scope="module")
def pg():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="doceflow-pg-"), cleanup_mode="stop")
    with psycopg.connect(server.get_uri(), autocommit=True) as conn:
        conn.execute(SHIM.read_text(encoding="utf-8"))
        conn.execute(MIGRATION.read_text(encoding="utf-8"))
        conn.execute(MIGRATION.read_text(encoding="utf-8"))  # idempotente
        conn.execute(SEED.read_text(encoding="utf-8"))
        conn.execute("insert into auth.users (id) values (%s), (%s)", (OWNER, INTRUDER))
        conn.execute("update public.confeitarias set owner_user_id = %s, whatsapp = '5511912345678'", (OWNER,))
        conn.execute("update public.produtos set disponivel = false where slug = 'bolo-geleia-artesanal'")
        conn.execute("insert into public.confeitarias (slug, nome, owner_user_id) values ('outra', 'Outra', %s)",
                     (INTRUDER,))
    yield server
    server.cleanup()


@pytest.fixture
def conn(pg):
    with psycopg.connect(pg.get_uri(), autocommit=True) as c:
        yield c


def as_anon(c):
    c.execute("reset role; select set_config('request.jwt.claim.sub', '', false); set role anon")


def as_user(c, user_id):
    c.execute("reset role")
    c.execute("select set_config('request.jwt.claim.sub', %s, false)", (str(user_id),))
    c.execute("set role authenticated")


def args(**o):
    d = dict(conf="kika-cakes", prod="docinhos-tradicionais", nome="Ana Teste", fone="5511987650000", qtd=2,
             data=date.today() + timedelta(days=7), modo="Retirada", obs="tema", origem="instagram", ok=True)
    d.update(o)
    return tuple(d.values())


def test_anon_creates_lead_with_status_novo_and_origin(conn):
    as_anon(conn)
    row = conn.execute(CALL, args()).fetchone()
    _id, protocolo, criado, *_rest, status, conf_nome, conf_whats = row
    assert criado is True and status == "Novo" and protocolo.startswith("DF-")
    assert conf_nome == "Kika Cakes" and conf_whats == "5511912345678"


def test_repeat_returns_same_lead(conn):
    as_anon(conn)
    a = conn.execute(CALL, args(fone="5511987651111")).fetchone()
    b = conn.execute(CALL, args(fone="5511987651111", obs="outra")).fetchone()
    assert a[1] == b[1] and b[2] is False


@pytest.mark.parametrize("override,code", [
    ({"prod": "bolo-geleia-artesanal"}, "produto_indisponivel"),
    ({"prod": "xxx"}, "produto_invalido"),
    ({"conf": "nao-existe"}, "confeitaria_invalida"),
    ({"qtd": 0}, "quantidade_invalida"),
    ({"data": date.today() - timedelta(days=1)}, "data_invalida"),
    ({"ok": False}, "consentimento_obrigatorio"),
    ({"fone": "123"}, "leads_cliente_whatsapp_check"),
    ({"modo": "Drone"}, "leads_modalidade_check"),
    ({"nome": "A", "fone": "5511987659999"}, "leads_cliente_nome_check"),  # fone novo: não cair na dedup
])
def test_server_validation(conn, override, code):
    as_anon(conn)
    with pytest.raises(psycopg.Error, match=code):
        conn.execute(CALL, args(**override))


def test_bad_origin_falls_back_to_site(conn):
    as_anon(conn)
    protocolo = conn.execute(CALL, args(fone="5511987652222", origem="<script>")).fetchone()[1]
    as_user(conn, OWNER)
    origem = conn.execute("select origem from public.leads where protocolo = %s", (protocolo,)).fetchone()[0]
    assert origem == "site"


@pytest.mark.parametrize("sql", [
    "select * from public.leads",
    "insert into public.leads (protocolo) values ('x')",
    "update public.leads set status = 'Fechado'",
    "delete from public.leads",
])
def test_anon_has_no_direct_access_to_leads(conn, sql):
    as_anon(conn)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(sql)


def test_anon_reads_catalog(conn):
    as_anon(conn)
    assert conn.execute("select count(*) from public.produtos").fetchone()[0] == 27
    assert conn.execute("select count(*) from public.confeitarias").fetchone()[0] == 2


def test_owner_sees_only_own_leads_and_can_update_status(conn):
    as_anon(conn)
    protocolo = conn.execute(CALL, args(fone="5511987653333")).fetchone()[1]
    as_user(conn, OWNER)
    protos = [r[0] for r in conn.execute("select protocolo from public.leads")]
    assert protocolo in protos
    conn.execute("update public.leads set status = 'Em contato' where protocolo = %s", (protocolo,))
    assert conn.execute("select status from public.leads where protocolo = %s", (protocolo,)).fetchone()[0] == \
        "Em contato"
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("update public.leads set cliente_nome = 'x'")


def test_other_store_owner_sees_nothing(conn):
    as_anon(conn)
    conn.execute(CALL, args(fone="5511987654444"))
    as_user(conn, INTRUDER)
    assert conn.execute("select count(*) from public.leads").fetchone()[0] == 0
    conn.execute("update public.leads set status = 'Perdido'")
    as_user(conn, OWNER)
    assert conn.execute("select count(*) from public.leads where status = 'Perdido'").fetchone()[0] == 0
