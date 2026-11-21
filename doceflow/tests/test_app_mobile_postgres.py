"""Backend do app (migrações 012 e 013) num PostgreSQL 16 real.

Mesmo cenário dos testes de segurança: Kika Cakes (dona A), "Outra Doceria" (dona B), um usuário
logado SEM perfil e o visitante. Cada teste roda numa transação desfeita no final.
"""

from datetime import date, timedelta

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("pgserver")

from tests.test_seguranca_postgres import (  # noqa: E402,F401  (fixtures reaproveitadas)
    LEAD,
    NO_PROFILE,
    ORDER,
    OWNER_A,
    OWNER_B,
    as_role,
    db,
    denied,
    ids,
    lead_args,
    order_args,
    pg,
    raises,
)

CONVERT = "select * from public.converter_orcamento_em_pedido(%s, %s, %s, %s, %s)"
INDICATORS = "select public.painel_indicadores(%s, %s)"
DEVICE = "select public.registrar_dispositivo(%s, %s)"
TOKEN = "fcm-token-de-teste-" + "x" * 40


def new_lead(db, phone="5511987658000", prod="docinhos-tradicionais"):
    as_role(db, "anon")
    return db.execute(LEAD, lead_args(phone=phone, prod=prod)).fetchone()[0]


def new_order(db, phone="5511987658500", **o):
    as_role(db, "anon")
    return db.execute(ORDER, order_args(phone=phone, **o)).fetchone()[0]


# ================================================================ indicadores
def test_indicators_count_only_own_store(db):
    new_order(db, phone="5511987658501")
    new_lead(db, phone="5511987658502")
    as_role(db, "authenticated", OWNER_A)
    a = db.execute(INDICATORS, (None, None)).fetchone()[0]
    db.execute("reset role")
    a_id, b_id = ids(db)
    expected_orders = db.execute("select count(*) from public.orders where confeitaria_id = %s", (a_id,)).fetchone()[0]
    expected_leads = db.execute("select count(*) from public.leads where confeitaria_id = %s", (a_id,)).fetchone()[0]
    assert a["confeitaria_id"] == str(a_id)
    assert a["pedidos"]["total"] == expected_orders and a["orcamentos"]["total"] == expected_leads
    assert a["pedidos"]["aguardando_confirmacao"] == expected_orders

    as_role(db, "authenticated", OWNER_B)
    b = db.execute(INDICATORS, (None, None)).fetchone()[0]
    assert b["confeitaria_id"] == str(b_id) and b["orcamentos"]["total"] == 0 and b["pedidos"]["total"] == 1


def test_indicators_values_match_panel_definitions(db):
    oid = new_order(db, phone="5511987658503")  # 50 × 6 + 2 × 150 = 600 estimado
    as_role(db, "authenticated", OWNER_A)
    before = db.execute(INDICATORS, (None, None)).fetchone()[0]["pedidos"]["valor_registrado"]
    db.execute("update public.orders set status = 'Cancelado' where id = %s", (oid,))
    after = db.execute(INDICATORS, (None, None)).fetchone()[0]["pedidos"]
    assert float(before) - float(after["valor_registrado"]) == 600.0  # cancelado não conta
    assert after["cancelados"] >= 1


def test_indicators_period_filter_and_conversion_rate(db):
    lid = new_lead(db, phone="5511987658504")
    as_role(db, "authenticated", OWNER_A)
    db.execute("update public.leads set status = 'Venda concluída' where id = %s", (lid,))
    tomorrow = date.today() + timedelta(days=2)
    future = db.execute(INDICATORS, (tomorrow, tomorrow + timedelta(days=1))).fetchone()[0]
    assert future["orcamentos"]["total"] == 0 and future["orcamentos"]["taxa_conversao"] is None
    today = db.execute(INDICATORS, (date.today() - timedelta(days=1), date.today() + timedelta(days=1))).fetchone()[0]
    leads = today["orcamentos"]
    assert leads["vendas_concluidas"] >= 1
    assert float(leads["taxa_conversao"]) == round(leads["vendas_concluidas"] / leads["total"], 4)


def test_indicators_reject_inverted_period(db):
    as_role(db, "authenticated", OWNER_A)
    raises(db, INDICATORS, (date.today(), date.today() - timedelta(days=1)), "periodo_invalido")


@pytest.mark.parametrize("role,user", [("authenticated", NO_PROFILE), ("anon", None)])
def test_indicators_denied_without_admin_profile(db, role, user):
    as_role(db, role, user)
    with pytest.raises(psycopg.Error, match="sem_permissao|permission denied"):
        db.execute(INDICATORS, (None, None))


# ================================================================ clientes
def test_clients_group_orders_and_quotes_by_whatsapp(db):
    phone = "5511987658600"
    new_order(db, phone=phone)
    new_lead(db, phone=phone)
    as_role(db, "authenticated", OWNER_A)
    row = db.execute("select total_pedidos, total_orcamentos, pedidos_em_andamento, valor_pedidos, cliente_nome "
                     "from public.clientes_resumo where cliente_whatsapp = %s", (phone,)).fetchall()
    assert len(row) == 1
    pedidos, orcamentos, andamento, valor, nome = row[0]
    assert (pedidos, orcamentos, andamento) == (1, 1, 1) and float(valor) == 600.0 and nome


@pytest.mark.parametrize("role,user", [("anon", None), ("authenticated", NO_PROFILE), ("authenticated", OWNER_B)])
def test_clients_hidden_from_others(db, role, user):
    phone = "5511987658601"
    new_order(db, phone=phone)
    as_role(db, role, user)
    assert denied(db, "select * from public.clientes_resumo where cliente_whatsapp = %s", (phone,))


@pytest.mark.parametrize("role,priv", [("authenticated", "insert"), ("authenticated", "update"),
                                       ("authenticated", "delete"), ("anon", "select")])
def test_clients_view_is_read_only(db, role, priv):
    db.execute("reset role")
    assert db.execute("select has_table_privilege(%s, 'public.clientes_resumo', %s)",
                      (role, priv)).fetchone()[0] is False


# ================================================================ orçamento -> pedido
def convert_args(lead_id, **o):
    d = dict(lead=lead_id, data=None, endereco="", valor=None, obs="")
    d.update(o)
    return tuple(d.values())


def test_owner_converts_quote_into_confirmed_order(db):
    lid = new_lead(db, phone="5511987658700")  # docinhos, Retirada, 2 caixas
    as_role(db, "authenticated", OWNER_A)
    oid, protocolo, criado, status = db.execute(CONVERT, convert_args(lid, valor=320, obs="Sinal pago")).fetchone()
    assert criado and status == "Confirmado" and protocolo.startswith("PD-")
    order = db.execute("select lead_id, valor_final, observacoes_internas, endereco_entrega, cliente_whatsapp "
                       "from public.orders where id = %s", (oid,)).fetchone()
    assert order[0] == lid and float(order[1]) == 320 and order[2] == "Sinal pago" and order[3] == ""
    assert order[4] == "5511987658700"
    item = db.execute("select produto_nome, quantidade, preco_unitario, subtotal from public.order_items "
                      "where order_id = %s", (oid,)).fetchall()
    assert len(item) == 1 and item[0][1] == 2 and float(item[0][3]) == float(item[0][2]) * 2
    assert db.execute("select status from public.leads where id = %s", (lid,)).fetchone()[0] == "Venda concluída"
    hist = db.execute("select campo, valor_novo, alterado_por from public.order_history where order_id = %s",
                      (oid,)).fetchall()
    assert hist == [("criado", "Confirmado", OWNER_A)]  # registra QUEM converteu


def test_converting_twice_returns_same_order(db):
    lid = new_lead(db, phone="5511987658701")
    as_role(db, "authenticated", OWNER_A)
    first = db.execute(CONVERT, convert_args(lid)).fetchone()
    second = db.execute(CONVERT, convert_args(lid, valor=999)).fetchone()
    assert second[0] == first[0] and second[2] is False
    assert db.execute("select count(*) from public.orders where lead_id = %s", (lid,)).fetchone()[0] == 1


def test_database_blocks_two_orders_for_one_quote(db):
    lid = new_lead(db, phone="5511987658702")
    as_role(db, "authenticated", OWNER_A)
    db.execute(CONVERT, convert_args(lid))
    db.execute("reset role")
    raises(db, "update public.orders set lead_id = %s where lead_id is null and confeitaria_id = "
               "(select confeitaria_id from public.leads where id = %s)", (lid, lid), "orders_lead_unico_idx")


@pytest.mark.parametrize("override,code", [
    ({"data": date.today() - timedelta(days=1)}, "data_invalida"),
    ({"valor": -1}, "valor_invalido"),
    ({"obs": "x" * 1001}, "observacoes_invalidas"),
])
def test_conversion_validation(db, override, code):
    lid = new_lead(db, phone="5511987658703")
    as_role(db, "authenticated", OWNER_A)
    raises(db, CONVERT, convert_args(lid, **override), code)


def test_delivery_quote_needs_address_to_convert(db):
    lid = new_lead(db, phone="5511987658704")
    db.execute("reset role")
    db.execute("update public.leads set modalidade = 'Entrega' where id = %s", (lid,))
    as_role(db, "authenticated", OWNER_A)
    raises(db, CONVERT, convert_args(lid, endereco="curto"), "endereco_obrigatorio")
    oid = db.execute(CONVERT, convert_args(lid, endereco="Rua das Flores, 123, Centro")).fetchone()[0]
    assert db.execute("select endereco_entrega from public.orders where id = %s", (oid,)).fetchone()[0] \
        == "Rua das Flores, 123, Centro"


def test_lost_quote_cannot_be_converted(db):
    lid = new_lead(db, phone="5511987658705")
    as_role(db, "authenticated", OWNER_A)
    db.execute("update public.leads set status = 'Perdido' where id = %s", (lid,))
    raises(db, CONVERT, convert_args(lid), "orcamento_perdido")


@pytest.mark.parametrize("role,user", [("authenticated", OWNER_B), ("authenticated", NO_PROFILE)])
def test_others_cannot_convert_and_learn_nothing(db, role, user):
    lid = new_lead(db, phone="5511987658706")
    as_role(db, role, user)
    raises(db, CONVERT, convert_args(lid), "orcamento_nao_encontrado")
    raises(db, CONVERT, convert_args("00000000-0000-0000-0000-000000000000"), "orcamento_nao_encontrado")


def test_visitor_cannot_convert(db):
    lid = new_lead(db, phone="5511987658707")
    as_role(db, "anon")
    raises(db, CONVERT, convert_args(lid), "permission denied")


def test_conversion_is_not_blocked_by_public_rate_limit(db):
    """Limite de envios vale para o site público, não para a ação da dona."""
    phone = "5511987658708"
    as_role(db, "anon")
    for i in range(5):
        db.execute(LEAD, ("kika-cakes", "docinhos-tradicionais", "Ana", phone, i + 1,
                          date.today() + timedelta(days=7), "Retirada", "", "site", True))
    db.execute("reset role")
    lid = db.execute("select id from public.leads where cliente_whatsapp = %s limit 1", (phone,)).fetchone()[0]
    as_role(db, "authenticated", OWNER_A)
    assert db.execute(CONVERT, convert_args(lid)).fetchone()[2] is True


# ================================================================ slug automático
def insert_product(db, nome, slug=None):
    a, _ = ids(db)
    as_role(db, "authenticated", OWNER_A)
    return db.execute("insert into public.produtos (confeitaria_id, slug, nome, categoria, unidade, tipo_preco) "
                      "values (%s, %s, %s, 'Bolos', 'kg', 'sob_consulta') returning slug", (a, slug, nome)).fetchone()[0]


def test_product_slug_generated_from_name_without_accents(db):
    assert insert_product(db, "Bolo de Maçã com Côco!") == "bolo-de-maca-com-coco"


def test_generated_slug_does_not_repeat_in_store(db):
    first = insert_product(db, "Pão de Mel")
    second = insert_product(db, "Pão de mel")
    assert (first, second) == ("pao-de-mel", "pao-de-mel-2")


def test_explicit_slug_is_kept(db):
    assert insert_product(db, "Qualquer nome", slug="meu-slug") == "meu-slug"


def test_slug_trigger_does_not_let_owner_write_other_store(db):
    _, b = ids(db)
    as_role(db, "authenticated", OWNER_A)
    assert denied(db, "insert into public.produtos (confeitaria_id, nome, categoria, unidade, tipo_preco) "
                      "values (%s, 'Invasão', 'Bolos', 'kg', 'sob_consulta')", (b,))


# ================================================================ dispositivos (013)
def test_owner_registers_device_once(db):
    as_role(db, "authenticated", OWNER_A)
    first = db.execute(DEVICE, (TOKEN, "android")).fetchone()[0]
    second = db.execute(DEVICE, (TOKEN, "android")).fetchone()[0]
    assert first == second
    rows = db.execute("select user_id, plataforma from public.admin_devices").fetchall()
    assert rows == [(OWNER_A, "android")]


def test_device_moves_to_the_last_account(db):
    as_role(db, "authenticated", OWNER_A)
    db.execute(DEVICE, (TOKEN, "android"))
    as_role(db, "authenticated", OWNER_B)
    db.execute(DEVICE, (TOKEN, "android"))
    assert db.execute("select count(*) from public.admin_devices").fetchone()[0] == 1  # B vê o seu
    as_role(db, "authenticated", OWNER_A)
    assert db.execute("select count(*) from public.admin_devices").fetchone()[0] == 0


def test_devices_private_to_each_user(db):
    as_role(db, "authenticated", OWNER_A)
    db.execute(DEVICE, (TOKEN, "android"))
    for role, user in (("authenticated", OWNER_B), ("authenticated", NO_PROFILE), ("anon", None)):
        as_role(db, role, user)
        assert denied(db, "select * from public.admin_devices")
        assert denied(db, "delete from public.admin_devices")


def test_owner_removes_own_device(db):
    as_role(db, "authenticated", OWNER_A)
    db.execute(DEVICE, (TOKEN, "android"))
    assert db.execute("delete from public.admin_devices where token = %s", (TOKEN,)).rowcount == 1


@pytest.mark.parametrize("sql", [
    "insert into public.admin_devices (user_id, confeitaria_id, token) "
    "select auth.uid(), id, 'token-direto-xxxxxxxxxxxxxxxx' from public.confeitarias limit 1",
    "update public.admin_devices set plataforma = 'ios'",
])
def test_devices_not_writable_directly(db, sql):
    as_role(db, "authenticated", OWNER_A)
    db.execute(DEVICE, (TOKEN, "android"))
    assert denied(db, sql)


@pytest.mark.parametrize("args,code", [
    (("curto", "android"), "token_invalido"),
    (("token com espaco " + "x" * 30, "android"), "token_invalido"),
    ((TOKEN, "windows"), "plataforma_invalida"),
])
def test_device_validation(db, args, code):
    as_role(db, "authenticated", OWNER_A)
    raises(db, DEVICE, args, code)


@pytest.mark.parametrize("role,user,match", [("authenticated", NO_PROFILE, "sem_permissao"),
                                             ("anon", None, "permission denied")])
def test_device_needs_admin_profile(db, role, user, match):
    as_role(db, role, user)
    raises(db, DEVICE, (TOKEN, "android"), match)


# ================================================================ nada público novo
@pytest.mark.parametrize("fn", ["painel_indicadores(date, date)",
                                "converter_orcamento_em_pedido(uuid, date, text, numeric, text)",
                                "registrar_dispositivo(text, text)", "produtos_slug_automatico()"])
def test_new_functions_not_executable_by_visitor(db, fn):
    db.execute("reset role")
    assert db.execute("select has_function_privilege('anon', %s, 'execute')", (f"public.{fn}",)).fetchone()[0] is False
