"""Camada de acesso a dados do DoceFlow.

- Produção: Supabase (PostgreSQL) com a chave anon e RLS. O schema está em
  `database/migrations/001_schema_leads.sql`. Leads só são criados pela função
  `criar_lead` (o visitante não lê nem grava a tabela `leads` diretamente).
- Testes locais: SQLite em arquivo, com o mesmo modelo de tabelas e as mesmas
  validações do servidor.

Todas as consultas são parametrizadas (SQLite com `?`, Supabase via SDK/RPC).
Os logs registram só protocolo e tipo de erro, nunca nome ou telefone.
"""

from __future__ import annotations

import logging
import secrets
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Protocol

from config import Settings, load_settings
from services.supabase_client import DatabaseConfigError, get_supabase_client  # noqa: F401 (reexportados)
from services import image_service
from services.image_service import MAX_IMAGES_PER_PRODUCT, ImageError
from services.product_service import PRICE_TYPES, SEED_PRODUCTS, Product
from services.quote_service import (
    DB_ERROR_MESSAGES,
    FULFILLMENT_OPTIONS,
    LEAD_STATUSES,
    MAX_DAYS_AHEAD,
    STATUS_NEW,
    Lead,
    LeadPersistenceError,
    LeadRequest,
    LeadValidationError,
    lead_fingerprint,
    normalize_br_whatsapp,
)

log = logging.getLogger("doceflow.database")


@dataclass
class DatabaseStatus:
    backend: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class Store:
    id: str
    slug: str
    name: str
    whatsapp: str | None


ORDER_ADMIN_COLUMNS = (
    "id", "protocolo", "created_at", "status", "status_atualizado_em", "cliente_nome", "cliente_whatsapp",
    "data_entrega", "modalidade", "observacoes", "observacoes_internas", "valor_estimado", "valor_final", "origem",
    "lead_id",
)

LEAD_ADMIN_COLUMNS = (
    "id", "protocolo", "created_at", "status", "status_atualizado_em", "cliente_nome", "cliente_whatsapp",
    "produto_nome", "quantidade", "unidade", "data_desejada", "modalidade", "observacoes", "origem",
)

# Campos do Product (app) -> colunas da tabela produtos
PRODUCT_COLUMNS = {
    "name": "nome", "category": "categoria", "description": "descricao", "unit": "unidade", "price": "preco",
    "price_type": "tipo_preco", "available": "disponivel", "image": "imagem", "min_qty": "qtd_min",
    "max_qty": "qtd_max", "order": "ordem", "published": "publicado", "featured": "destaque",
    "production_days": "prazo_producao_dias",
}

PRODUCT_IN_USE = ("Este produto já tem orçamentos ou pedidos registrados e não pode ser excluído "
                  "(o histórico seria perdido). Despublique-o para tirá-lo da vitrine.")
IMAGE_COLUMNS = "id,produto_id,storage_path,alt_text,principal,ordem"


def _first_photo_by_product(rows: list[dict]) -> dict[str, str]:
    """Foto principal de cada produto; sem principal marcada, a primeira pela ordem."""
    best: dict[str, dict] = {}
    for r in rows:
        pid = str(r["produto_id"])
        cur = best.get(pid)
        if cur is None or (bool(r["principal"]), -int(r["ordem"])) > (bool(cur["principal"]), -int(cur["ordem"])):
            best[pid] = r
    return {pid: r["storage_path"] for pid, r in best.items()}


class AdminAccessError(PermissionError):
    """Usuário autenticado sem confeitaria vinculada (ou sem permissão)."""


def _product_db_values(data: dict) -> dict:
    return {col: data[key] for key, col in PRODUCT_COLUMNS.items() if key in data}


class Repository(Protocol):
    backend: str

    def get_store(self) -> Store | None: ...
    def list_products(self) -> list[Product]: ...
    def create_lead(self, request: LeadRequest) -> Lead: ...
    def list_leads(self) -> list[dict]: ...
    def update_lead_status(self, lead_id: str, status: str) -> None: ...
    def create_product(self, data: dict) -> str: ...
    def update_product(self, product_id: str, data: dict) -> None: ...
    def delete_product(self, product_id: str) -> None: ...
    def list_product_images(self, product_id: str) -> list[dict]: ...
    def add_product_image(self, product_id: str, data: bytes, alt_text: str = "") -> dict: ...
    def set_principal_image(self, image_id: str) -> None: ...
    def delete_product_image(self, image_id: str) -> None: ...


# =================================================================== SQLite
SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS confeitarias (
    id          TEXT PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,
    nome        TEXT NOT NULL,
    whatsapp    TEXT,
    ativo       INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS produtos (
    id              TEXT PRIMARY KEY,
    confeitaria_id  TEXT NOT NULL REFERENCES confeitarias(id) ON DELETE CASCADE,
    slug            TEXT NOT NULL,
    nome            TEXT NOT NULL,
    categoria       TEXT NOT NULL,
    descricao       TEXT NOT NULL DEFAULT '',
    unidade         TEXT NOT NULL,
    preco           REAL CHECK (preco IS NULL OR preco >= 0),
    tipo_preco      TEXT NOT NULL CHECK (tipo_preco IN ('a_partir_de','estimado','sob_consulta')),
    disponivel      INTEGER NOT NULL DEFAULT 1,
    publicado       INTEGER NOT NULL DEFAULT 1,
    destaque        INTEGER NOT NULL DEFAULT 0,
    prazo_producao_dias INTEGER CHECK (prazo_producao_dias IS NULL OR prazo_producao_dias BETWEEN 0 AND 90),
    imagem          TEXT,
    qtd_min         INTEGER NOT NULL DEFAULT 1 CHECK (qtd_min >= 1),
    qtd_max         INTEGER NOT NULL DEFAULT 50 CHECK (qtd_max >= qtd_min),
    ordem           INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    UNIQUE (confeitaria_id, slug)
);

CREATE TABLE IF NOT EXISTS leads (
    id                TEXT PRIMARY KEY,
    protocolo         TEXT NOT NULL UNIQUE,
    confeitaria_id    TEXT NOT NULL REFERENCES confeitarias(id) ON DELETE CASCADE,
    produto_id        TEXT NOT NULL REFERENCES produtos(id) ON DELETE RESTRICT,
    produto_nome      TEXT NOT NULL,
    unidade           TEXT NOT NULL,
    quantidade        INTEGER NOT NULL CHECK (quantidade > 0),
    data_desejada     TEXT NOT NULL,
    modalidade        TEXT NOT NULL CHECK (modalidade IN ('Retirada','Entrega')),
    observacoes       TEXT NOT NULL DEFAULT '' CHECK (length(observacoes) <= 500),
    cliente_nome      TEXT NOT NULL CHECK (length(cliente_nome) BETWEEN 2 AND 80),
    cliente_whatsapp  TEXT NOT NULL CHECK (cliente_whatsapp GLOB '55[0-9]*'
                                           AND length(cliente_whatsapp) IN (12, 13)),
    consentimento     INTEGER NOT NULL CHECK (consentimento = 1),
    consentimento_em  TEXT NOT NULL,
    origem            TEXT NOT NULL DEFAULT 'site',
    status            TEXT NOT NULL DEFAULT 'Novo'
                      CHECK (status IN ('Novo','Em atendimento','Orçamento enviado','Venda concluída','Perdido')),
    status_atualizado_em TEXT,
    fingerprint       TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE (confeitaria_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS leads_confeitaria_created_idx ON leads (confeitaria_id, created_at DESC);

-- Metadados das fotos. Os arquivos ficam em disco (pasta product_images ao lado do banco),
-- nunca dentro do banco, como no Supabase Storage.
CREATE TABLE IF NOT EXISTS product_images (
    id              TEXT PRIMARY KEY,
    confeitaria_id  TEXT NOT NULL REFERENCES confeitarias(id) ON DELETE CASCADE,
    produto_id      TEXT NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    storage_path    TEXT NOT NULL UNIQUE,
    alt_text        TEXT NOT NULL DEFAULT '' CHECK (length(alt_text) <= 200),
    principal       INTEGER NOT NULL DEFAULT 0,
    ordem           INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS product_images_uma_principal ON product_images (produto_id) WHERE principal = 1;
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_protocol() -> str:
    brt = datetime.now(timezone.utc) - timedelta(hours=3)
    return f"DF-{brt:%y%m%d}-{secrets.token_hex(3).upper()}"


def get_sqlite_connection(settings: Settings | None = None) -> sqlite3.Connection:
    settings = settings or load_settings()
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


class SQLiteRepository:
    """Repositório local (testes). Sempre filtra pela confeitaria configurada."""

    backend = "sqlite"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.store_slug = settings.store_slug
        try:
            with closing(get_sqlite_connection(settings)) as conn, conn:
                _migrate_sqlite_statuses(conn)
                _migrate_sqlite_published(conn)
                conn.executescript(SQLITE_SCHEMA)
                self._seed(conn)
        except sqlite3.Error as exc:
            log.error("Falha ao preparar SQLite: %s", type(exc).__name__)
            raise LeadPersistenceError("Banco local indisponível.") from exc

    def _connect(self) -> sqlite3.Connection:
        return get_sqlite_connection(self.settings)

    def _seed(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT id FROM confeitarias WHERE slug = ?", (self.store_slug,)).fetchone()
        if row:
            return
        now = _now_iso()
        store_id = str(uuid.uuid4())
        whatsapp = normalize_br_whatsapp(self.settings.whatsapp_number or "")
        conn.execute(
            "INSERT INTO confeitarias (id, slug, nome, whatsapp, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (store_id, self.store_slug, self.settings.store_name, whatsapp, now, now),
        )
        conn.executemany(
            """INSERT INTO produtos (id, confeitaria_id, slug, nome, categoria, descricao, unidade, preco,
                                     tipo_preco, disponivel, imagem, qtd_min, qtd_max, ordem, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (str(uuid.uuid4()), store_id, p.slug, p.name, p.category, p.description, p.unit, p.price,
                 p.price_type, int(p.available), p.image, p.min_qty, p.max_qty, p.order, now, now)
                for p in SEED_PRODUCTS
            ],
        )

    def _store_row(self, conn: sqlite3.Connection) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT id, slug, nome, whatsapp FROM confeitarias WHERE slug = ? AND ativo = 1", (self.store_slug,)
        ).fetchone()

    def get_store(self) -> Store | None:
        with closing(self._connect()) as conn:
            row = self._store_row(conn)
        if row is None:
            return None
        whatsapp = row["whatsapp"] or normalize_br_whatsapp(self.settings.whatsapp_number or "")
        return Store(row["id"], row["slug"], row["nome"], whatsapp)

    def list_products(self) -> list[Product]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """SELECT p.* FROM produtos p JOIN confeitarias c ON c.id = p.confeitaria_id
                   WHERE c.slug = ? AND c.ativo = 1 ORDER BY p.ordem, p.nome""",
                (self.store_slug,),
            ).fetchall()
            images = conn.execute(
                f"""SELECT {IMAGE_COLUMNS} FROM product_images
                    WHERE confeitaria_id = (SELECT id FROM confeitarias WHERE slug = ?)""", (self.store_slug,)
            ).fetchall()
        first = _first_photo_by_product([dict(i) for i in images])
        photos = {pid: self._local_file(path) for pid, path in first.items()}
        return [_product_from_row(dict(r), photos.get(str(r["id"]))) for r in rows]

    def create_lead(self, request: LeadRequest) -> Lead:
        try:
            with closing(self._connect()) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                store = self._store_row(conn)
                if store is None:
                    raise LeadValidationError(DB_ERROR_MESSAGES["confeitaria_invalida"])
                product = conn.execute(
                    "SELECT * FROM produtos WHERE confeitaria_id = ? AND slug = ?",
                    (store["id"], request.product_slug),
                ).fetchone()
                _server_side_checks(request, product)

                fp = lead_fingerprint(request.whatsapp, product["id"], request.quantity,
                                      request.desired_date, request.fulfillment)
                existing = conn.execute(
                    "SELECT id FROM leads WHERE confeitaria_id = ? AND fingerprint = ?", (store["id"], fp)
                ).fetchone()
                created = existing is None
                if created:
                    lead_id, now = str(uuid.uuid4()), _now_iso()
                    conn.execute(
                        """INSERT INTO leads (id, protocolo, confeitaria_id, produto_id, produto_nome, unidade,
                               quantidade, data_desejada, modalidade, observacoes, cliente_nome, cliente_whatsapp,
                               consentimento, consentimento_em, origem, status, fingerprint, created_at, updated_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?)""",
                        (lead_id, _new_protocol(), store["id"], product["id"], product["nome"], product["unidade"],
                         request.quantity, request.desired_date.isoformat(), request.fulfillment, request.notes,
                         request.customer_name, request.whatsapp, now, request.origin, STATUS_NEW, fp, now, now),
                    )
                else:
                    lead_id = existing["id"]
                row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        except (LeadValidationError, LeadPersistenceError):
            raise
        except sqlite3.IntegrityError as exc:
            log.warning("Lead recusado pelo banco local: %s", type(exc).__name__)
            raise LeadValidationError("Não foi possível validar os dados do pedido. Confira os campos.") from exc
        except sqlite3.Error as exc:
            log.error("Falha ao gravar lead (sqlite): %s", type(exc).__name__)
            raise LeadPersistenceError("Não foi possível registrar a solicitação.") from exc

        store_obj = self.get_store()
        lead = Lead(
            id=row["id"], protocol=row["protocolo"], created=created, product_name=row["produto_nome"],
            unit=row["unidade"], quantity=row["quantidade"], desired_date=date.fromisoformat(row["data_desejada"]),
            fulfillment=row["modalidade"], notes=row["observacoes"], customer_name=row["cliente_nome"],
            status=row["status"], store_name=store_obj.name, store_whatsapp=store_obj.whatsapp,
        )
        log.info("Lead %s protocolo=%s", "criado" if created else "reaproveitado", lead.protocol)
        return lead

    def list_leads(self) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                f"""SELECT {', '.join('l.' + c for c in LEAD_ADMIN_COLUMNS)}
                    FROM leads l JOIN confeitarias c ON c.id = l.confeitaria_id
                    WHERE c.slug = ? ORDER BY l.created_at DESC""",
                (self.store_slug,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------- painel
    def update_lead_status(self, lead_id: str, status: str) -> None:
        if status not in LEAD_STATUSES:
            raise LeadValidationError("Status inválido.")
        now = _now_iso()
        try:
            with closing(self._connect()) as conn, conn:
                cur = conn.execute(
                    """UPDATE leads SET status = ?, updated_at = ?,
                              status_atualizado_em = CASE WHEN status <> ? THEN ? ELSE status_atualizado_em END
                       WHERE id = ? AND confeitaria_id = (SELECT id FROM confeitarias WHERE slug = ?)""",
                    (status, now, status, now, lead_id, self.store_slug),
                )
        except sqlite3.Error as exc:
            log.error("Falha ao atualizar status (sqlite): %s", type(exc).__name__)
            raise LeadPersistenceError("Não foi possível salvar o status.") from exc
        if cur.rowcount != 1:
            raise LeadValidationError("Lead não encontrado nesta confeitaria.")
        log.info("Status de lead atualizado para %s", status)

    def create_product(self, data: dict) -> None:
        values = _product_db_values(data)
        now = _now_iso()
        try:
            with closing(self._connect()) as conn, conn:
                store = self._store_row(conn)
                cols = ["id", "confeitaria_id", "slug", *values.keys(), "created_at", "updated_at"]
                new_id = str(uuid.uuid4())
                conn.execute(
                    f"INSERT INTO produtos ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                    (new_id, store["id"], data["slug"], *values.values(), now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise LeadValidationError("Produto inválido ou já existente.") from exc
        except sqlite3.Error as exc:
            log.error("Falha ao criar produto (sqlite): %s", type(exc).__name__)
            raise LeadPersistenceError("Não foi possível salvar o produto.") from exc
        return new_id

    def update_product(self, product_id: str, data: dict) -> None:
        values = _product_db_values(data)
        try:
            with closing(self._connect()) as conn, conn:
                cur = conn.execute(
                    f"""UPDATE produtos SET {', '.join(f'{c} = ?' for c in values)}, updated_at = ?
                        WHERE id = ? AND confeitaria_id = (SELECT id FROM confeitarias WHERE slug = ?)""",
                    (*values.values(), _now_iso(), product_id, self.store_slug),
                )
        except sqlite3.IntegrityError as exc:
            raise LeadValidationError("Dados do produto inválidos.") from exc
        except sqlite3.Error as exc:
            log.error("Falha ao atualizar produto (sqlite): %s", type(exc).__name__)
            raise LeadPersistenceError("Não foi possível salvar o produto.") from exc
        if cur.rowcount != 1:
            raise LeadValidationError("Produto não encontrado nesta confeitaria.")

    # ------------------------------------------------------------- exclusão e fotos (local)
    @property
    def _images_dir(self):
        return self.settings.sqlite_path.parent / "product_images"

    def _local_file(self, storage_path: str) -> str | None:
        base = self._images_dir.resolve()
        path = (base / storage_path).resolve()
        if base not in path.parents or not path.exists():
            return None
        return str(path)

    def _store_product(self, conn, product_id: str) -> tuple[str, str]:
        row = conn.execute(
            """SELECT p.id, p.confeitaria_id FROM produtos p JOIN confeitarias c ON c.id = p.confeitaria_id
               WHERE p.id = ? AND c.slug = ?""", (product_id, self.store_slug)).fetchone()
        if row is None:
            raise LeadValidationError("Produto não encontrado nesta confeitaria.")
        return row["id"], row["confeitaria_id"]

    def delete_product(self, product_id: str) -> None:
        try:
            with closing(self._connect()) as conn, conn:
                self._store_product(conn, product_id)
                if conn.execute("SELECT 1 FROM leads WHERE produto_id = ? LIMIT 1", (product_id,)).fetchone():
                    raise LeadValidationError(PRODUCT_IN_USE)
                paths = [r[0] for r in conn.execute("SELECT storage_path FROM product_images WHERE produto_id = ?",
                                                     (product_id,))]
                conn.execute("DELETE FROM produtos WHERE id = ?", (product_id,))
        except sqlite3.IntegrityError as exc:
            raise LeadValidationError(PRODUCT_IN_USE) from exc
        except sqlite3.Error as exc:
            log.error("Falha ao excluir produto (sqlite): %s", type(exc).__name__)
            raise LeadPersistenceError("Não foi possível excluir o produto.") from exc
        for path in paths:
            (self._images_dir / path).unlink(missing_ok=True)

    def list_product_images(self, product_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            self._store_product(conn, product_id)
            rows = conn.execute(f"SELECT {IMAGE_COLUMNS} FROM product_images WHERE produto_id = ? ORDER BY ordem",
                                (product_id,)).fetchall()
        return [{**dict(r), "principal": bool(r["principal"]), "url": self._local_file(r["storage_path"])}
                for r in rows]

    def add_product_image(self, product_id: str, data: bytes, alt_text: str = "") -> dict:
        clean, ext, _ = image_service.prepare_image(data)
        image_id = str(uuid.uuid4())
        with closing(self._connect()) as conn, conn:
            pid, store_id = self._store_product(conn, product_id)
            count, last, has_main = conn.execute(
                "SELECT count(*), max(ordem), max(principal) FROM product_images WHERE produto_id = ?", (pid,)
            ).fetchone()
            if count >= MAX_IMAGES_PER_PRODUCT:
                raise ImageError(f"Cada produto pode ter no máximo {MAX_IMAGES_PER_PRODUCT} fotos.")
            path = image_service.image_path(store_id, pid, image_id, ext)
            row = {"id": image_id, "confeitaria_id": store_id, "produto_id": pid, "storage_path": path,
                   "alt_text": alt_text[:200], "principal": not has_main, "ordem": (last or 0) + 1}
            file = self._images_dir / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(clean)
            try:
                conn.execute("INSERT INTO product_images (id, confeitaria_id, produto_id, storage_path, alt_text, "
                             "principal, ordem, created_at) VALUES (?,?,?,?,?,?,?,?)",
                             (*row.values(), _now_iso()))
            except sqlite3.Error as exc:
                file.unlink(missing_ok=True)
                raise ImageError("Não foi possível registrar a foto.") from exc
        return {**row, "url": str(file)}

    def set_principal_image(self, image_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT produto_id FROM product_images WHERE id = ?", (image_id,)).fetchone()
            if row is None:
                raise ImageError("Foto não encontrada nesta confeitaria.")
            self._store_product(conn, row["produto_id"])
            conn.execute("UPDATE product_images SET principal = 0 WHERE produto_id = ?", (row["produto_id"],))
            conn.execute("UPDATE product_images SET principal = 1 WHERE id = ?", (image_id,))

    def delete_product_image(self, image_id: str) -> None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute("SELECT produto_id, storage_path, principal FROM product_images WHERE id = ?",
                               (image_id,)).fetchone()
            if row is None:
                raise ImageError("Foto não encontrada nesta confeitaria.")
            self._store_product(conn, row["produto_id"])
            conn.execute("DELETE FROM product_images WHERE id = ?", (image_id,))
            if row["principal"]:  # promove a próxima foto para principal
                conn.execute("""UPDATE product_images SET principal = 1 WHERE id = (
                                  SELECT id FROM product_images WHERE produto_id = ? ORDER BY ordem LIMIT 1)""",
                             (row["produto_id"],))
        (self._images_dir / row["storage_path"]).unlink(missing_ok=True)

    # ------------------------------------------------------------- pedidos
    # Pedidos dependem da função criar_pedido e do RLS do Supabase (migração 007).
    # O SQLite local (testes) não os emula: mensagem clara em vez de comportamento parcial.
    def _orders_unavailable(self, *args, **kwargs):
        raise LeadPersistenceError("Pedidos estão disponíveis só com o Supabase (DB_BACKEND=supabase).")

    create_order = list_orders = update_order = _orders_unavailable


def _migrate_sqlite_published(conn: sqlite3.Connection) -> None:
    """Bancos locais anteriores às colunas novas de produtos (equivalente às migrações 005 e 009)."""
    exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='produtos'").fetchone()
    if not exists:
        return
    cols = {r[1] for r in conn.execute("PRAGMA table_info(produtos)")}
    for col, ddl in (("publicado", "INTEGER NOT NULL DEFAULT 1"), ("destaque", "INTEGER NOT NULL DEFAULT 0"),
                     ("prazo_producao_dias", "INTEGER")):
        if col not in cols:
            conn.execute(f"ALTER TABLE produtos ADD COLUMN {col} {ddl}")


def _migrate_sqlite_statuses(conn: sqlite3.Connection) -> None:
    """Converte bancos locais da etapa 03 para o funil da etapa 04 (SQLite não altera CHECK)."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='leads'").fetchone()
    if row is None or "Em contato" not in row[0]:
        return
    conn.execute("ALTER TABLE leads RENAME TO leads_v3")
    conn.executescript(SQLITE_SCHEMA)
    conn.execute(
        """INSERT INTO leads (id, protocolo, confeitaria_id, produto_id, produto_nome, unidade, quantidade,
               data_desejada, modalidade, observacoes, cliente_nome, cliente_whatsapp, consentimento,
               consentimento_em, origem, status, fingerprint, created_at, updated_at)
           SELECT id, protocolo, confeitaria_id, produto_id, produto_nome, unidade, quantidade, data_desejada,
               modalidade, observacoes, cliente_nome, cliente_whatsapp, consentimento, consentimento_em, origem,
               CASE status WHEN 'Em contato' THEN 'Em atendimento' WHEN 'Fechado' THEN 'Venda concluída'
                           ELSE status END,
               fingerprint, created_at, updated_at
           FROM leads_v3"""
    )
    conn.execute("DROP TABLE leads_v3")
    log.info("Banco local migrado para os status da etapa 04")


def _server_side_checks(request: LeadRequest, product: sqlite3.Row | None) -> None:
    """Espelha as validações da função SQL criar_lead."""
    if product is None or not product["publicado"]:
        raise LeadValidationError(DB_ERROR_MESSAGES["produto_invalido"])
    if not product["disponivel"]:
        raise LeadValidationError(DB_ERROR_MESSAGES["produto_indisponivel"])
    if not (product["qtd_min"] <= request.quantity <= product["qtd_max"]):
        raise LeadValidationError(DB_ERROR_MESSAGES["quantidade_invalida"])
    today = date.today()
    if not (today <= request.desired_date <= today + timedelta(days=MAX_DAYS_AHEAD)):
        raise LeadValidationError(DB_ERROR_MESSAGES["data_invalida"])
    if request.fulfillment not in FULFILLMENT_OPTIONS:
        raise LeadValidationError("Escolha retirada ou entrega.")
    if not request.consent:
        raise LeadValidationError(DB_ERROR_MESSAGES["consentimento_obrigatorio"])


def _product_from_row(row: dict, photo: str | None = None) -> Product:
    price_type = row["tipo_preco"] if row["tipo_preco"] in PRICE_TYPES else "sob_consulta"
    return Product(
        slug=row["slug"], name=row["nome"], category=row["categoria"], description=row.get("descricao") or "",
        unit=row["unidade"], price=float(row["preco"]) if row.get("preco") is not None else None,
        price_type=price_type, available=bool(row["disponivel"]), image=row.get("imagem"),
        min_qty=int(row["qtd_min"]), max_qty=int(row["qtd_max"]), id=str(row["id"]), order=int(row.get("ordem") or 0),
        published=bool(row["publicado"]) if row.get("publicado") is not None else True,
        featured=bool(row.get("destaque") or False),
        production_days=int(row["prazo_producao_dias"]) if row.get("prazo_producao_dias") is not None else None,
        photo=photo,
    )


# ================================================================= Supabase
# O cliente fica em supabase_client.py; reexportado aqui por compatibilidade.
class SupabaseRepository:
    """Repositório de produção. Usa só a chave anon; o acesso é limitado pelo RLS."""

    backend = "supabase"

    def __init__(self, client, store_slug: str):
        self.client = client
        self.store_slug = store_slug

    def get_store(self) -> Store | None:
        try:
            res = (self.client.table("confeitarias").select("id,slug,nome,whatsapp")
                   .eq("slug", self.store_slug).limit(1).execute())
        except Exception as exc:
            log.error("Falha ao ler confeitaria: %s", type(exc).__name__)
            raise LeadPersistenceError("Catálogo indisponível no momento.") from exc
        if not res.data:
            return None
        r = res.data[0]
        return Store(str(r["id"]), r["slug"], r["nome"], r.get("whatsapp"))

    def list_products(self) -> list[Product]:
        store = self.get_store()
        if store is None:
            return []
        try:
            res = (self.client.table("produtos").select("*")
                   .eq("confeitaria_id", store.id).order("ordem").execute())
        except Exception as exc:
            log.error("Falha ao ler produtos: %s", type(exc).__name__)
            raise LeadPersistenceError("Catálogo indisponível no momento.") from exc
        photos: dict[str, str] = {}
        try:  # o visitante só recebe fotos de produtos publicados (RLS da migração 006)
            imgs = (self.client.table("product_images").select(IMAGE_COLUMNS)
                    .eq("confeitaria_id", store.id).execute())
            photos = {pid: image_service.public_url(self.client, path)
                      for pid, path in _first_photo_by_product(imgs.data or []).items()}
        except Exception as exc:  # sem fotos o catálogo continua funcionando (imagem padrão)
            log.warning("Fotos de produtos indisponíveis: %s", type(exc).__name__)
        return [_product_from_row(r, photos.get(str(r["id"]))) for r in res.data or []]

    def create_lead(self, request: LeadRequest) -> Lead:
        params = {
            "p_confeitaria_slug": self.store_slug,
            "p_produto_slug": request.product_slug,
            "p_cliente_nome": request.customer_name,
            "p_cliente_whatsapp": request.whatsapp,
            "p_quantidade": request.quantity,
            "p_data_desejada": request.desired_date.isoformat(),
            "p_modalidade": request.fulfillment,
            "p_observacoes": request.notes,
            "p_origem": request.origin,
            "p_consentimento": bool(request.consent),
        }
        try:
            res = self.client.rpc("criar_lead", params).execute()
        except Exception as exc:
            raise _translate_supabase_error(exc) from exc
        rows = res.data or []
        if not rows:
            log.error("criar_lead não retornou dados")
            raise LeadPersistenceError("Não foi possível confirmar o registro da solicitação.")
        r = rows[0]
        lead = Lead(
            id=str(r["id"]), protocol=r["protocolo"], created=bool(r["criado"]), product_name=r["produto_nome"],
            unit=r["unidade"], quantity=int(r["quantidade"]), desired_date=date.fromisoformat(str(r["data_desejada"])),
            fulfillment=r["modalidade"], notes=r.get("observacoes") or "", customer_name=r["cliente_nome"],
            status=r["status"], store_name=r["confeitaria_nome"], store_whatsapp=r.get("confeitaria_whatsapp"),
        )
        log.info("Lead %s protocolo=%s", "criado" if lead.created else "reaproveitado", lead.protocol)
        return lead

    def list_leads(self) -> list[dict]:
        """Só retorna dados com um usuário autenticado dono da confeitaria (RLS)."""
        store = self.get_store()
        if store is None:
            return []
        res = (self.client.table("leads").select(",".join(LEAD_ADMIN_COLUMNS))
               .eq("confeitaria_id", store.id).order("created_at", desc=True).execute())
        return res.data or []

    # ------------------------------------------------------------- painel
    @classmethod
    def for_owner(cls, client, user_id: str, store_slug: str | None = None) -> "SupabaseRepository":
        """Repositório da confeitaria do perfil administrativo ATIVO do usuário logado.

        A autorização real é do banco (RLS com is_store_admin). Aqui só descobrimos a
        confeitaria do perfil, que o usuário consegue ler mas não alterar.
        """
        try:
            profile = (client.table("admin_profiles").select("confeitaria_id,papel")
                       .eq("user_id", user_id).eq("ativo", True).limit(1).execute())
            if not profile.data:
                raise AdminAccessError("Este usuário não está vinculado a nenhuma confeitaria.")
            query = (client.table("confeitarias").select("slug")
                     .eq("id", profile.data[0]["confeitaria_id"]).eq("ativo", True))
            if store_slug:
                query = query.eq("slug", store_slug)
            res = query.limit(1).execute()
        except AdminAccessError:
            raise
        except Exception as exc:
            log.error("Falha ao localizar confeitaria da usuária: %s", type(exc).__name__)
            raise LeadPersistenceError("Não foi possível carregar a confeitaria.") from exc
        if not res.data:
            raise AdminAccessError("Este usuário não está vinculado a esta confeitaria.")
        return cls(client, res.data[0]["slug"])

    def _require_store(self) -> Store:
        store = self.get_store()
        if store is None:
            raise AdminAccessError("Confeitaria não encontrada.")
        return store

    def _write(self, query, what: str):
        try:
            res = query.execute()
        except Exception as exc:
            raise _translate_supabase_error(exc) from exc
        if not res.data:
            # RLS filtra linhas de outra confeitaria: o update não afeta nada
            raise LeadValidationError(f"{what} não encontrado nesta confeitaria.")
        return res

    def update_lead_status(self, lead_id: str, status: str) -> None:
        if status not in LEAD_STATUSES:
            raise LeadValidationError("Status inválido.")
        store = self._require_store()
        self._write(self.client.table("leads").update({"status": status})
                    .eq("id", lead_id).eq("confeitaria_id", store.id), "Lead")
        log.info("Status de lead atualizado para %s", status)

    def create_product(self, data: dict) -> None:
        store = self._require_store()
        row = {"confeitaria_id": store.id, "slug": data["slug"], **_product_db_values(data)}
        res = self._write(self.client.table("produtos").insert(row), "Produto")
        return str(res.data[0]["id"])

    def update_product(self, product_id: str, data: dict) -> None:
        store = self._require_store()
        self._write(self.client.table("produtos").update(_product_db_values(data))
                    .eq("id", product_id).eq("confeitaria_id", store.id), "Produto")

    # ------------------------------------------------------------- exclusão e fotos (migrações 006 e 009)
    def delete_product(self, product_id: str) -> None:
        store = self._require_store()
        paths = [r["storage_path"] for r in self._image_rows(store, product_id)]
        try:
            res = self.client.table("produtos").delete().eq("id", product_id).eq("confeitaria_id", store.id).execute()
        except Exception as exc:
            if str(getattr(exc, "code", "")) == "23503":  # orçamentos/pedidos apontam para o produto
                raise LeadValidationError(PRODUCT_IN_USE) from exc
            raise _translate_supabase_error(exc) from exc
        if not res.data:
            raise LeadValidationError("Produto não encontrado nesta confeitaria.")
        image_service.remove_files(self.client, paths)  # os registros já saíram em cascata

    def _image_rows(self, store: Store, product_id: str) -> list[dict]:
        try:
            res = (self.client.table("product_images").select(IMAGE_COLUMNS).eq("produto_id", product_id)
                   .eq("confeitaria_id", store.id).order("ordem").execute())
        except Exception as exc:
            log.error("Falha ao ler fotos: %s", type(exc).__name__)
            raise ImageError("Não foi possível carregar as fotos agora.") from exc
        return res.data or []

    def list_product_images(self, product_id: str) -> list[dict]:
        rows = self._image_rows(self._require_store(), product_id)
        return [{**r, "url": image_service.public_url(self.client, r["storage_path"])} for r in rows]

    def add_product_image(self, product_id: str, data: bytes, alt_text: str = "") -> dict:
        store = self._require_store()
        current = self._image_rows(store, product_id)
        if len(current) >= MAX_IMAGES_PER_PRODUCT:
            raise ImageError(f"Cada produto pode ter no máximo {MAX_IMAGES_PER_PRODUCT} fotos.")
        order = max((int(r["ordem"]) for r in current), default=0) + 1
        row = image_service.upload_product_image(self.client, store.id, product_id, data, alt_text,
                                                 principal=not any(r["principal"] for r in current), order=order)
        return {**row, "url": image_service.public_url(self.client, row["storage_path"])}

    def set_principal_image(self, image_id: str) -> None:
        try:
            self.client.rpc("definir_foto_principal", {"p_image_id": image_id}).execute()
        except Exception as exc:
            log.error("Falha ao definir foto principal: %s", type(exc).__name__)
            raise ImageError("Não foi possível definir a foto principal.") from exc

    def delete_product_image(self, image_id: str) -> None:
        store = self._require_store()
        try:
            res = (self.client.table("product_images").select(IMAGE_COLUMNS).eq("id", image_id)
                   .eq("confeitaria_id", store.id).execute())
        except Exception as exc:
            raise ImageError("Não foi possível apagar a foto agora.") from exc
        if not res.data:
            raise ImageError("Foto não encontrada nesta confeitaria.")
        row = res.data[0]
        image_service.delete_product_image(self.client, row)
        if row["principal"]:  # promove a próxima foto para principal
            rest = self._image_rows(store, str(row["produto_id"]))
            if rest:
                self.set_principal_image(str(rest[0]["id"]))


    # ------------------------------------------------------------- pedidos (migração 007)
    def create_order(self, request):
        """Fluxo público: grava pedido + itens pela função criar_pedido (sem leitura das tabelas)."""
        from services.order_service import Order

        params = {
            "p_confeitaria_slug": self.store_slug, "p_cliente_nome": request.customer_name,
            "p_cliente_whatsapp": request.whatsapp, "p_data_entrega": request.delivery_date.isoformat(),
            "p_modalidade": request.fulfillment, "p_observacoes": request.notes, "p_itens": request.rpc_items(),
            "p_origem": request.origin, "p_consentimento": bool(request.consent),
        }
        try:
            res = self.client.rpc("criar_pedido", params).execute()
        except Exception as exc:
            raise _translate_supabase_error(exc) from exc
        if not res.data:
            raise LeadPersistenceError("Não foi possível confirmar o registro do pedido.")
        r = res.data[0]
        log.info("Pedido %s protocolo=%s", "criado" if r["criado"] else "reaproveitado", r["protocolo"])
        return Order(id=str(r["id"]), protocol=r["protocolo"], created=bool(r["criado"]), status=r["status"],
                     estimated_total=float(r["valor_estimado"]) if r.get("valor_estimado") is not None else None,
                     store_name=r["confeitaria_nome"], store_whatsapp=r.get("confeitaria_whatsapp"))

    def list_orders(self) -> list[dict]:
        """Pedidos da confeitaria com os itens (o RLS só devolve linhas da administradora logada)."""
        store = self._require_store()
        try:
            orders = (self.client.table("orders").select(",".join(ORDER_ADMIN_COLUMNS))
                      .eq("confeitaria_id", store.id).order("created_at", desc=True).execute()).data or []
            ids = [o["id"] for o in orders]
            items = (self.client.table("order_items")
                     .select("order_id,produto_nome,unidade,quantidade,preco_unitario,tipo_preco")
                     .in_("order_id", ids).execute()).data if ids else []
        except Exception as exc:
            raise _translate_supabase_error(exc) from exc
        by_order: dict[str, list] = {}
        for item in items or []:
            by_order.setdefault(item["order_id"], []).append(item)
        for o in orders:
            o["itens"] = by_order.get(o["id"], [])
        return orders

    def update_order(self, order_id: str, fields: dict) -> None:
        from services.order_service import validate_order_update

        try:
            clean = validate_order_update(fields)
        except ValueError as exc:
            raise LeadValidationError(str(exc)) from exc
        store = self._require_store()
        self._write(self.client.table("orders").update(clean).eq("id", order_id).eq("confeitaria_id", store.id),
                    "Pedido")


def _translate_supabase_error(exc: Exception) -> Exception:
    message = str(getattr(exc, "message", "") or exc)
    code = str(getattr(exc, "code", "") or "")
    for key, friendly in DB_ERROR_MESSAGES.items():
        if key in message:
            return LeadValidationError(friendly)
    if code in {"23514", "23502", "22P02", "22023", "22007", "22008"}:
        log.warning("Lead recusado pelo banco: código %s", code)
        return LeadValidationError("Não foi possível validar os dados do pedido. Confira os campos.")
    log.error("Falha ao gravar lead (supabase): %s %s", type(exc).__name__, code)
    return LeadPersistenceError("Não foi possível registrar a solicitação.")


# =================================================================== fábrica
def get_repository(settings: Settings | None = None) -> Repository:
    settings = settings or load_settings()
    if settings.db_backend == "supabase":
        return SupabaseRepository(get_supabase_client(settings), settings.store_slug)
    if settings.db_backend == "sqlite":
        return SQLiteRepository(settings)
    raise DatabaseConfigError("DB_BACKEND deve ser 'supabase' ou 'sqlite'.")


def check_connection(settings: Settings | None = None) -> DatabaseStatus:
    """Testa a conexão sem expor credenciais na mensagem de retorno."""
    settings = settings or load_settings()
    try:
        repo = get_repository(settings)
        store = repo.get_store()
    except DatabaseConfigError as exc:
        return DatabaseStatus(settings.db_backend, False, str(exc))
    except Exception as exc:
        return DatabaseStatus(settings.db_backend, False, f"Falha ao conectar: {type(exc).__name__}")
    if store is None:
        return DatabaseStatus(settings.db_backend, False, f"Confeitaria '{settings.store_slug}' não encontrada.")
    label = "SQLite local (somente testes)." if settings.db_backend == "sqlite" else "Supabase conectado."
    return DatabaseStatus(settings.db_backend, True, label)
