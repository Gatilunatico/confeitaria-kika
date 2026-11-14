"""Etapa 3 (gestão de produtos): regras da migração 009 num PostgreSQL 16 real.

Mesmo cenário dos testes de segurança (duas confeitarias, duas donas, usuário sem perfil
e visitante), reaproveitando as fixtures de test_seguranca_postgres.
"""

import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("pgserver")

from tests.test_seguranca_postgres import (  # noqa: E402,F401  (fixtures reaproveitadas)
    NO_PROFILE,
    OWNER_A,
    OWNER_B,
    _obj,
    as_role,
    db,
    denied,
    ids,
    pg,
    raises,
)


def prod(db, slug):
    db.execute("reset role")
    return db.execute("select id from public.produtos where slug = %s", (slug,)).fetchone()[0]


def add_image(db, store, product, principal=False):
    path = f"{store}/{product}/{uuid.uuid4()}.jpg"
    return db.execute("insert into public.product_images (confeitaria_id, produto_id, storage_path, principal) "
                      "values (%s,%s,%s,%s) returning id", (store, product, path, principal)).fetchone()[0]


# ================================================================ cadastro e edição
def test_owner_sets_featured_and_production_time(db):
    pid = prod(db, "cupcake-tag")
    as_role(db, "authenticated", OWNER_A)
    cur = db.execute("update public.produtos set destaque = true, prazo_producao_dias = 3 where id = %s", (pid,))
    assert cur.rowcount == 1
    as_role(db, "anon")  # o visitante vê o destaque e o prazo de um produto publicado
    assert db.execute("select destaque, prazo_producao_dias from public.produtos where id = %s",
                      (pid,)).fetchone() == (True, 3)


def test_production_time_is_checked_by_database(db):
    pid = prod(db, "cupcake-tag")
    as_role(db, "authenticated", OWNER_A)
    raises(db, "update public.produtos set prazo_producao_dias = %s where id = %s", (91, pid), "prazo_producao")


def test_owner_creates_product_with_new_fields(db):
    a, _ = ids(db)
    as_role(db, "authenticated", OWNER_A)
    db.execute("""insert into public.produtos (confeitaria_id, slug, nome, categoria, unidade, preco, tipo_preco,
                  destaque, prazo_producao_dias, publicado)
                  values (%s, 'torta-nova', 'Torta Nova', 'Tortas', 'kg', 90, 'a_partir_de', true, 5, false)""", (a,))
    as_role(db, "anon")  # cadastrado como rascunho: invisível até publicar
    assert db.execute("select count(*) from public.produtos where slug = 'torta-nova'").fetchone()[0] == 0
    as_role(db, "authenticated", OWNER_A)
    db.execute("update public.produtos set publicado = true where slug = 'torta-nova'")
    as_role(db, "anon")
    assert db.execute("select count(*) from public.produtos where slug = 'torta-nova'").fetchone()[0] == 1


@pytest.mark.parametrize("role,user", [("anon", None), ("authenticated", NO_PROFILE), ("authenticated", OWNER_B)])
def test_others_cannot_change_featured_or_production_time(db, role, user):
    pid = prod(db, "cupcake-tag")
    as_role(db, role, user)
    assert denied(db, "update public.produtos set destaque = true, prazo_producao_dias = 1 where id = %s", (pid,))


# ================================================================ exclusão
def test_owner_deletes_product_without_history_and_its_photo_records(db):
    a, _ = ids(db)
    pid = prod(db, "cupcake-tag")
    as_role(db, "authenticated", OWNER_A)
    add_image(db, a, pid, principal=True)
    assert db.execute("delete from public.produtos where id = %s", (pid,)).rowcount == 1
    assert db.execute("select count(*) from public.product_images where produto_id = %s", (pid,)).fetchone()[0] == 0


def test_product_with_orders_or_leads_cannot_be_deleted(db):
    as_role(db, "authenticated", OWNER_A)
    for slug in ("bem-casado", "docinhos-tradicionais"):  # têm pedido e orçamento registrados
        pid = prod(db, slug)
        as_role(db, "authenticated", OWNER_A)
        db.execute("savepoint s")
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            db.execute("delete from public.produtos where id = %s", (pid,))
        db.execute("rollback to savepoint s")


@pytest.mark.parametrize("role,user", [("anon", None), ("authenticated", NO_PROFILE), ("authenticated", OWNER_B)])
def test_others_cannot_delete_products(db, role, user):
    pid = prod(db, "cupcake-tag")
    as_role(db, role, user)
    assert denied(db, "delete from public.produtos where id = %s", (pid,))
    db.execute("reset role")
    assert db.execute("select count(*) from public.produtos where id = %s", (pid,)).fetchone()[0] == 1


# ================================================================ fotos
def test_photo_limit_enforced_by_database(db):
    a, _ = ids(db)
    pid = prod(db, "cupcake-tag")
    as_role(db, "authenticated", OWNER_A)
    for _ in range(10):
        add_image(db, a, pid)
    raises(db, "insert into public.product_images (confeitaria_id, produto_id, storage_path) values (%s,%s,%s)",
           (a, pid, f"{a}/{pid}/{uuid.uuid4()}.jpg"), "limite_fotos")


def test_owner_switches_principal_photo_atomically(db):
    a, _ = ids(db)
    pid = prod(db, "cupcake-tag")
    as_role(db, "authenticated", OWNER_A)
    first = add_image(db, a, pid, principal=True)
    second = add_image(db, a, pid)
    db.execute("select public.definir_foto_principal(%s)", (second,))
    rows = dict(db.execute("select id, principal from public.product_images where produto_id = %s", (pid,)))
    assert rows == {first: False, second: True}


@pytest.mark.parametrize("role,user,match", [
    ("authenticated", OWNER_B, "foto_invalida"),
    ("authenticated", NO_PROFILE, "foto_invalida"),
    ("anon", None, "permission denied"),
])
def test_others_cannot_switch_principal_photo(db, role, user, match):
    a, _ = ids(db)
    pid = prod(db, "cupcake-tag")
    as_role(db, "authenticated", OWNER_A)
    image = add_image(db, a, pid, principal=True)
    as_role(db, role, user)
    raises(db, "select public.definir_foto_principal(%s)", (image,), match)


@pytest.mark.parametrize("role,user", [("anon", None), ("authenticated", NO_PROFILE), ("authenticated", OWNER_B)])
def test_others_cannot_overwrite_or_delete_photos(db, role, user):
    a, _ = ids(db)
    pid = prod(db, "cupcake-tag")
    path = f"{a}/{pid}/{uuid.uuid4()}.jpg"
    as_role(db, "authenticated", OWNER_A)
    assert _obj(db, "product-images", path)
    add_image(db, a, pid, principal=True)
    as_role(db, role, user)
    assert denied(db, "delete from public.product_images where produto_id = %s", (pid,))
    assert denied(db, "update public.product_images set principal = false where produto_id = %s", (pid,))
    assert denied(db, "update storage.objects set name = name where bucket_id = 'product-images'")
    assert denied(db, "delete from storage.objects where bucket_id = 'product-images'")
    db.execute("reset role")
    assert db.execute("select count(*) from storage.objects where name = %s", (path,)).fetchone()[0] == 1


def test_visitor_sees_photos_only_of_published_products(db):
    a, _ = ids(db)
    pid = prod(db, "cupcake-tag")
    as_role(db, "authenticated", OWNER_A)
    add_image(db, a, pid, principal=True)
    as_role(db, "anon")
    assert db.execute("select count(*) from public.product_images where produto_id = %s", (pid,)).fetchone()[0] == 1
    as_role(db, "authenticated", OWNER_A)
    db.execute("update public.produtos set publicado = false where id = %s", (pid,))
    as_role(db, "anon")
    assert db.execute("select count(*) from public.product_images where produto_id = %s", (pid,)).fetchone()[0] == 0
