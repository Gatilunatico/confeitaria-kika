"""Migração 014 (publicação no Instagram) num PostgreSQL 16 real.

Cenário dos testes de segurança: Kika Cakes (dona A), Outra Doceria (dona B), usuário sem perfil
e visitante. O "serviço" é a conexão sem papel (postgres), como a conexão de banco do servidor.
"""

import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("pgserver")

from tests.test_seguranca_postgres import (  # noqa: E402,F401
    NO_PROFILE,
    OWNER_A,
    OWNER_B,
    as_role,
    db,
    denied,
    ids,
    pg,
    raises,
)

SCHEDULE = "select * from public.agendar_publicacao_instagram(%s, %s, %s)"
TOKEN = "IGAA" + "x" * 60


def new_post(db, store, formato="feed", legenda="Bolo de pote! #kikacakes"):
    db.execute("reset role")
    pid = uuid.uuid4()
    db.execute("""insert into public.marketing_posts (id, confeitaria_id, produto_nome, template, formato, tom, legenda,
                  imagem_path) values (%s, %s, 'Bolo de Pote', 'produto', %s, 'amigavel', %s, %s)""",
               (pid, store, formato, legenda, f"{store}/{pid}.png"))
    return pid


def connect(db, store, token=TOKEN):
    db.execute("reset role")
    db.execute("select public.instagram_salvar_conexao(%s, '178414', 'kikacakes_confeitaria', 'business', %s, %s)",
               (store, token, datetime.now(timezone.utc) + timedelta(days=60)))


def schedule(db, post, key="toque-0001", when=None, user=OWNER_A):
    as_role(db, "authenticated", user)
    return db.execute(SCHEDULE, (post, when, key)).fetchone()


# ================================================================ conexão e token
def test_token_goes_to_vault_and_app_never_reads_it(db):
    a, _ = ids(db)
    connect(db, a)
    secret = db.execute("select token_vault_id from public.instagram_accounts where confeitaria_id = %s", (a,)).fetchone()[0]
    assert db.execute("select decrypted_secret from vault.decrypted_secrets where id = %s", (secret,)).fetchone()[0] == TOKEN
    as_role(db, "authenticated", OWNER_A)
    row = db.execute("select username, status, account_type from public.instagram_accounts").fetchone()
    assert row == ("kikacakes_confeitaria", "conectado", "business")
    assert denied(db, "select token_vault_id from public.instagram_accounts")
    assert denied(db, "select * from vault.decrypted_secrets")
    assert denied(db, "select * from public.instagram_token(%s)", (a,))


def test_reconnect_updates_same_secret(db):
    a, _ = ids(db)
    connect(db, a)
    connect(db, a, token="IGAA" + "y" * 60)
    db.execute("reset role")
    assert db.execute("select count(*) from vault.secrets where name = %s", (f"instagram_token_{a}",)).fetchone()[0] == 1
    assert db.execute("select token from public.instagram_token(%s)", (a,)).fetchone()[0].endswith("y" * 60)


@pytest.mark.parametrize("role,user", [("anon", None), ("authenticated", OWNER_A), ("authenticated", NO_PROFILE)])
@pytest.mark.parametrize("fn", [
    "instagram_criar_estado(text, uuid, uuid, interval)", "instagram_consumir_estado(text)",
    "instagram_salvar_conexao(uuid, text, text, text, text, timestamptz)", "instagram_token(uuid)",
    "instagram_reservar_publicacoes(text, integer, interval)", "instagram_concluir_publicacao(uuid, text, text)",
    "instagram_registrar_falha(uuid, text, text, boolean, interval)", "instagram_marcar_verificar(uuid, text)",
    "instagram_salvar_container(uuid, text)", "instagram_contas_para_renovar(interval)",
    "instagram_marcar_conta_erro(uuid, text)", "instagram_log(uuid, text, text)",
])
def test_service_functions_are_not_executable_by_app(db, role, user, fn):
    db.execute("reset role")
    assert db.execute("select has_function_privilege(%s, %s, 'execute')", (role, f"public.{fn}")).fetchone()[0] is False


def test_oauth_state_is_single_use_and_expires(db):
    a, _ = ids(db)
    db.execute("reset role")
    h1, h2 = "a" * 64, "b" * 64
    db.execute("select public.instagram_criar_estado(%s, %s, %s, interval '10 minutes')", (h1, a, OWNER_A))
    db.execute("select public.instagram_criar_estado(%s, %s, %s, interval '-1 minute')", (h2, a, OWNER_A))
    assert db.execute("select * from public.instagram_consumir_estado(%s)", (h1,)).fetchone() == (a, OWNER_A)
    assert db.execute("select * from public.instagram_consumir_estado(%s)", (h1,)).fetchone() is None  # já usado
    assert db.execute("select * from public.instagram_consumir_estado(%s)", (h2,)).fetchone() is None  # vencido


# ================================================================ agendamento (app)
def test_owner_schedules_and_same_key_returns_same(db):
    a, _ = ids(db)
    connect(db, a)
    post = new_post(db, a)
    first = schedule(db, post)
    again = schedule(db, post)
    assert first[0] == again[0]
    as_role(db, "authenticated", OWNER_A)
    rows = db.execute("select status, legenda, formato from public.instagram_publications").fetchall()
    assert rows == [("agendado", "Bolo de pote! #kikacakes", "feed")]
    assert db.execute("select evento from public.instagram_publication_logs").fetchall() == [("agendado",)]


def test_only_one_active_schedule_per_post(db):
    a, _ = ids(db)
    connect(db, a)
    post = new_post(db, a)
    schedule(db, post, key="toque-0001")
    as_role(db, "authenticated", OWNER_A)
    raises(db, SCHEDULE, (post, None, "toque-0002"), "publicacao_ja_agendada")


def test_story_is_scheduled_without_caption(db):
    a, _ = ids(db)
    connect(db, a)
    post = new_post(db, a, formato="story")
    schedule(db, post)
    db.execute("reset role")
    assert db.execute("select legenda from public.instagram_publications").fetchone()[0] == ""


@pytest.mark.parametrize("override,code", [
    ({"connected": False}, "instagram_desconectado"),
    ({"when": datetime.now(timezone.utc) - timedelta(days=1)}, "data_invalida"),
    ({"when": datetime.now(timezone.utc) + timedelta(days=90)}, "data_invalida"),
    ({"key": "curta"}, "chave_invalida"),
])
def test_schedule_validation(db, override, code):
    a, _ = ids(db)
    if override.get("connected", True):
        connect(db, a)
    post = new_post(db, a)
    as_role(db, "authenticated", OWNER_A)
    raises(db, SCHEDULE, (post, override.get("when"), override.get("key", "toque-0001")), code)


@pytest.mark.parametrize("role,user", [("authenticated", OWNER_B), ("authenticated", NO_PROFILE)])
def test_others_cannot_schedule_or_see(db, role, user):
    a, _ = ids(db)
    connect(db, a)
    post = new_post(db, a)
    schedule(db, post)
    as_role(db, role, user)
    expected = "post_nao_encontrado" if user == OWNER_B else "sem_permissao"
    raises(db, SCHEDULE, (post, None, "toque-9999"), expected)
    assert denied(db, "select * from public.instagram_publications")
    assert denied(db, "select * from public.instagram_publication_logs")


def test_visitor_has_no_access(db):
    as_role(db, "anon")
    assert denied(db, "select * from public.instagram_publications")
    raises(db, SCHEDULE, (uuid.uuid4(), None, "toque-0001"), "permission denied")


@pytest.mark.parametrize("sql", [
    "update public.instagram_publications set status = 'publicado'",
    "insert into public.instagram_publications (confeitaria_id, marketing_post_id, formato, imagem_path, agendado_para, idempotency_key) "
    "select confeitaria_id, marketing_post_id, formato, imagem_path, now(), 'direto-0001' from public.instagram_publications",
    "delete from public.instagram_publications",
    "insert into public.instagram_publication_logs (publication_id, confeitaria_id, evento) "
    "select id, confeitaria_id, 'falso' from public.instagram_publications",
])
def test_owner_cannot_write_queue_directly(db, sql):
    a, _ = ids(db)
    connect(db, a)
    schedule(db, new_post(db, a))
    as_role(db, "authenticated", OWNER_A)
    assert denied(db, sql)


def test_cancel_and_retry(db):
    a, _ = ids(db)
    connect(db, a)
    pub = schedule(db, new_post(db, a))[0]
    as_role(db, "authenticated", OWNER_A)
    db.execute("select public.cancelar_publicacao_instagram(%s)", (pub,))
    raises(db, "select public.cancelar_publicacao_instagram(%s)", (pub,), "publicacao_nao_cancelavel")
    raises(db, "select public.tentar_publicacao_instagram_novamente(%s)", (pub,), "publicacao_nao_falhou")
    db.execute("reset role")
    db.execute("update public.instagram_publications set status = 'falhou', tentativas = 3 where id = %s", (pub,))
    as_role(db, "authenticated", OWNER_A)
    db.execute("select public.tentar_publicacao_instagram_novamente(%s)", (pub,))
    assert db.execute("select status, tentativas from public.instagram_publications where id = %s",
                      (pub,)).fetchone() == ("agendado", 0)


def test_disconnect_deletes_token_and_cancels_queue(db):
    a, _ = ids(db)
    connect(db, a)
    pub = schedule(db, new_post(db, a))[0]
    as_role(db, "authenticated", OWNER_A)
    db.execute("select public.desconectar_instagram()")
    db.execute("reset role")
    assert db.execute("select count(*) from vault.secrets").fetchone()[0] == 0
    assert db.execute("select status, token_vault_id from public.instagram_accounts").fetchone() == ("desconectado", None)
    assert db.execute("select status from public.instagram_publications where id = %s", (pub,)).fetchone()[0] == "cancelado"


# ================================================================ serviço (fila)
def test_never_published_without_media_id(db):
    a, _ = ids(db)
    connect(db, a)
    pub = schedule(db, new_post(db, a))[0]
    db.execute("reset role")
    raises(db, "update public.instagram_publications set status = 'publicado' where id = %s", (pub,),
           "instagram_publications_publicado_check")
    db.execute("select * from public.instagram_reservar_publicacoes('w1', 5)")
    raises(db, "select public.instagram_concluir_publicacao(%s, '', null)", (pub,), "media_id_obrigatorio")
    db.execute("select public.instagram_concluir_publicacao(%s, '1790001', 'https://www.instagram.com/p/abc/')", (pub,))
    assert db.execute("select status, ig_media_id from public.instagram_publications where id = %s",
                      (pub,)).fetchone() == ("publicado", "1790001")


def test_temporary_failures_retry_until_limit(db):
    a, _ = ids(db)
    connect(db, a)
    pub = schedule(db, new_post(db, a))[0]
    db.execute("reset role")
    statuses = []
    for _ in range(3):
        db.execute("update public.instagram_publications set proxima_tentativa_em = now() - interval '1 second' where id = %s", (pub,))
        assert db.execute("select count(*) from public.instagram_reservar_publicacoes('w1', 5)").fetchone()[0] == 1
        statuses.append(db.execute("select public.instagram_registrar_falha(%s, 'meta_2', 'instável', true, interval '0')",
                                   (pub,)).fetchone()[0])
    assert statuses == ["agendado", "agendado", "falhou"]  # max_tentativas = 3
    logs = [r[0] for r in db.execute("select evento from public.instagram_publication_logs where publication_id = %s order by id",
                                     (pub,))]
    assert logs == ["agendado", "nova_tentativa_agendada", "nova_tentativa_agendada", "falhou"]


def test_future_schedule_is_not_reserved_early(db):
    a, _ = ids(db)
    connect(db, a)
    schedule(db, new_post(db, a), when=datetime.now(timezone.utc) + timedelta(hours=2))
    db.execute("reset role")
    assert db.execute("select count(*) from public.instagram_reservar_publicacoes('w1', 5)").fetchone()[0] == 0


def test_stuck_publishing_is_reclaimed_and_can_go_to_verify(db):
    a, _ = ids(db)
    connect(db, a)
    pub = schedule(db, new_post(db, a))[0]
    db.execute("reset role")
    db.execute("select * from public.instagram_reservar_publicacoes('w1', 5)")
    assert db.execute("select count(*) from public.instagram_reservar_publicacoes('w2', 5)").fetchone()[0] == 0
    db.execute("update public.instagram_publications set bloqueado_em = now() - interval '1 hour' where id = %s", (pub,))
    assert db.execute("select bloqueado_por from public.instagram_reservar_publicacoes('w2', 5)").fetchone()[0] == "w2"
    db.execute("select public.instagram_marcar_verificar(%s, 'confirmar')", (pub,))
    assert db.execute("select status from public.instagram_publications where id = %s", (pub,)).fetchone()[0] == "verificar"


def test_two_workers_never_take_the_same_item(pg):
    """Concorrência real: duas conexões reservam ao mesmo tempo; cada item vai para uma só."""
    with psycopg.connect(pg.get_uri(), autocommit=True) as c:
        a = c.execute("select id from public.confeitarias where slug = 'kika-cakes'").fetchone()[0]
        c.execute("select public.instagram_salvar_conexao(%s, '1', 'kika', 'business', %s, now() + interval '60 days')",
                  (a, TOKEN))
        c.execute("update public.instagram_publications set status = 'cancelado' where status in ('agendado','publicando')")
        posts = []
        for i in range(6):
            pid = uuid.uuid4()
            c.execute("""insert into public.marketing_posts (id, confeitaria_id, produto_nome, template, formato, tom,
                         imagem_path) values (%s, %s, 'X', 'produto', 'feed', 'amigavel', %s)""", (pid, a, f"{a}/{pid}.png"))
            c.execute("""insert into public.instagram_publications (confeitaria_id, marketing_post_id, formato, imagem_path,
                         agendado_para, idempotency_key) values (%s, %s, 'feed', %s, now(), %s)""",
                      (a, pid, f"{a}/{pid}.png", f"concorrencia-{i:04d}-{pid.hex[:8]}"))
            posts.append(pid)
    got: dict[str, list] = {}
    barrier = threading.Barrier(2)

    def take(name):
        with psycopg.connect(pg.get_uri(), autocommit=True) as c:
            barrier.wait()
            got[name] = [r[0] for r in c.execute("select marketing_post_id from public.instagram_reservar_publicacoes(%s, 4)",
                                                 (name,))]

    threads = [threading.Thread(target=take, args=(n,)) for n in ("w1", "w2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    taken = got["w1"] + got["w2"]
    assert len(taken) == 6 and len(set(taken)) == 6  # todos reservados, nenhum repetido
    with psycopg.connect(pg.get_uri(), autocommit=True) as c:  # limpa para os outros testes
        c.execute("delete from public.instagram_publications where idempotency_key like 'concorrencia-%'")
        c.execute("delete from public.marketing_posts where produto_nome = 'X'")
        c.execute("delete from vault.secrets")
        c.execute("delete from public.instagram_accounts")
