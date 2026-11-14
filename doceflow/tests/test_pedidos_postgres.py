"""Etapa 4 (pedidos): migração 010 num PostgreSQL 16 real (status, endereço, preços, histórico, acesso).

Mesmo cenário dos testes de segurança (duas confeitarias, duas donas, usuário sem perfil e visitante).
"""

import json
from datetime import date, timedelta

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("pgserver")

from tests.test_seguranca_postgres import (  # noqa: E402,F401  (fixtures reaproveitadas)
    NO_PROFILE,
    ORDER,
    OWNER_A,
    OWNER_B,
    as_role,
    db,
    denied,
    ids,
    order_args,
    pg,
    raises,
)


def new_order(db, phone="5511987659000", **o):
    as_role(db, "anon")
    return db.execute(ORDER, order_args(phone=phone, **o)).fetchone()[0]


def test_new_order_waits_for_confirmation_and_logs_creation(db):
    oid = new_order(db)
    db.execute("reset role")
    assert db.execute("select status from public.orders where id = %s", (oid,)).fetchone()[0] == \
        "Aguardando confirmação"
    rows = db.execute("select campo, valor_novo, alterado_por from public.order_history where order_id = %s",
                      (oid,)).fetchall()
    assert rows == [("criado", "Aguardando confirmação", None)]  # criado pelo cliente (sem usuário)


def test_items_keep_name_and_price_from_the_moment_of_the_order(db):
    oid = new_order(db)
    db.execute("reset role")
    db.execute("update public.produtos set nome = 'Bem-casado NOVO', preco = 99 where slug = 'bem-casado'")
    item = db.execute("""select produto_nome, preco_unitario, quantidade, subtotal from public.order_items
                         where order_id = %s and produto_nome like 'Bem%%'""", (oid,)).fetchone()
    assert item[0] != "Bem-casado NOVO" and float(item[1]) == 6.0
    assert float(item[3]) == float(item[1]) * item[2]  # subtotal calculado pelo banco


def test_price_comes_from_database_not_from_browser(db):
    """O navegador só manda slug e quantidade; campos extras de preço são ignorados."""
    itens = [{"produto_slug": "bem-casado", "quantidade": 50, "preco": 0.01, "preco_unitario": 0.01}]
    oid = new_order(db, phone="5511987659001", itens=itens)
    db.execute("reset role")
    total, unit = db.execute("""select o.valor_estimado, i.preco_unitario from public.orders o
                                join public.order_items i on i.order_id = o.id where o.id = %s""", (oid,)).fetchone()
    assert float(unit) == 6.0 and float(total) == 300.0


def test_pickup_does_not_store_address(db):
    oid = new_order(db, phone="5511987659002", modo="Retirada", endereco="Rua que não deveria ser guardada, 1")
    db.execute("reset role")
    assert db.execute("select endereco_entrega from public.orders where id = %s", (oid,)).fetchone()[0] == ""


def test_delivery_stores_address(db):
    oid = new_order(db, phone="5511987659003")
    db.execute("reset role")
    assert db.execute("select endereco_entrega from public.orders where id = %s",
                      (oid,)).fetchone()[0].startswith("Rua das Flores")


def test_on_request_item_leaves_estimate_empty(db):
    db.execute("update public.produtos set tipo_preco = 'sob_consulta' where slug = 'docinhos-tradicionais'")
    oid = new_order(db, phone="5511987659004")
    db.execute("reset role")
    assert db.execute("select valor_estimado from public.orders where id = %s", (oid,)).fetchone()[0] is None


def test_old_status_is_no_longer_accepted(db):
    oid = new_order(db, phone="5511987659005")
    db.execute("reset role")
    raises(db, "update public.orders set status = 'Recebido' where id = %s", (oid,), "orders_status_check")


# ================================================================ gestão e histórico
def test_owner_updates_order_and_history_records_who_and_what(db):
    oid = new_order(db, phone="5511987659006")
    as_role(db, "authenticated", OWNER_A)
    db.execute("update public.orders set status = 'Confirmado', valor_final = 420, data_entrega = %s, "
               "observacoes_internas = 'Sinal combinado' where id = %s", (date.today() + timedelta(days=20), oid))
    rows = db.execute("select campo, valor_anterior, valor_novo, alterado_por from public.order_history "
                      "where order_id = %s and campo <> 'criado' order by campo", (oid,)).fetchall()
    assert [r[0] for r in rows] == ["data_entrega", "observacoes_internas", "status", "valor_final"]
    status_row = next(r for r in rows if r[0] == "status")
    assert status_row[1:] == ("Aguardando confirmação", "Confirmado", OWNER_A)


@pytest.mark.parametrize("sql", [
    "update public.orders set valor_estimado = 1 where id = %s",       # valor calculado pelo servidor
    "update public.orders set cliente_whatsapp = '5511900000000' where id = %s",
    "update public.orders set confeitaria_id = gen_random_uuid() where id = %s",
    "update public.order_items set preco_unitario = 0 where order_id = %s",
    "delete from public.orders where id = %s",
])
def test_owner_cannot_tamper_with_registered_values(db, sql):
    oid = new_order(db, phone="5511987659007")
    as_role(db, "authenticated", OWNER_A)
    assert denied(db, sql, (oid,))


def test_history_cannot_be_written_or_rewritten(db):
    oid = new_order(db, phone="5511987659008")
    a, _ = ids(db)
    as_role(db, "authenticated", OWNER_A)
    assert denied(db, "insert into public.order_history (order_id, confeitaria_id, campo) values (%s, %s, 'status')",
                  (oid, a))
    assert denied(db, "update public.order_history set valor_novo = 'x' where order_id = %s", (oid,))
    assert denied(db, "delete from public.order_history where order_id = %s", (oid,))


@pytest.mark.parametrize("role,user", [("anon", None), ("authenticated", NO_PROFILE), ("authenticated", OWNER_B)])
def test_others_cannot_see_or_change_orders(db, role, user):
    oid = new_order(db, phone="5511987659009")
    as_role(db, role, user)
    for table in ("orders", "order_items", "order_history"):
        col = "id" if table == "orders" else "order_id"
        assert denied(db, f"select * from public.{table} where {col} = %s", (oid,))
    assert denied(db, "update public.orders set status = 'Cancelado' where id = %s", (oid,))


def test_customer_only_gets_back_their_own_order(db):
    as_role(db, "anon")
    row = db.execute(ORDER, order_args(phone="5511987659010")).fetchall()
    assert len(row) == 1  # a função devolve só o pedido recém-criado, nada de terceiros


def test_items_from_other_store_rejected(db):
    as_role(db, "anon")
    raises(db, ORDER, order_args(phone="5511987659011", itens=[{"produto_slug": "bem-casado", "quantidade": 50},
                                                              {"produto_slug": "bolo-b", "quantidade": 2}]),
           "produto_invalido")
    db.execute("reset role")
    assert db.execute("select count(*) from public.orders where cliente_whatsapp = '5511987659011'").fetchone()[0] == 0


def test_items_payload_must_be_a_list(db):
    as_role(db, "anon")
    args = list(order_args(phone="5511987659012"))
    args[6] = json.dumps({"produto_slug": "bem-casado", "quantidade": 50})
    raises(db, ORDER, tuple(args), "itens_invalidos")
