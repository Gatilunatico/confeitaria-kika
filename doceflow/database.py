"""Camada de acesso a dados do DoceFlow.

- Produção: Supabase (PostgreSQL) com a chave anon e RLS. O schema está em
  `supabase/migrations/001_schema_leads.sql`. Leads só são criados pela função
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
from services.catalog import PRICE_TYPES, SEED_PRODUCTS, Product
from services.leads import (
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


class DatabaseConfigError(RuntimeError):
    """Configuração de banco ausente ou inválida."""


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


LEAD_ADMIN_COLUMNS = (
    "id", "protocolo", "created_at", "status", "status_atualizado_em", "cliente_nome", "cliente_whatsapp",
    "produto_nome", "quantidade", "unidade", "data_desejada", "modalidade", "observacoes", "origem",
)

# Campos do Product (app) -> colunas da tabela produtos
PRODUCT_COLUMNS = {
    "name": "nome", "category": "categoria", "description": "descricao", "unit": "unidade", "price": "preco",
    "price_type": "tipo_preco", "available": "disponivel", "image": "imagem", "min_qty": "qtd_min",
    "max_qty": "qtd_max", "order": "ordem",
}


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
    def create_product(self, data: dict) -> None: ...
    def update_product(self, product_id: str, data: dict) -> None: ...


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
        return [_product_from_row(dict(r)) for r in rows]

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
                conn.execute(
                    f"INSERT INTO produtos ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                    (str(uuid.uuid4()), store["id"], data["slug"], *values.values(), now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise LeadValidationError("Produto inválido ou já existente.") from exc
        except sqlite3.Error as exc:
            log.error("Falha ao criar produto (sqlite): %s", type(exc).__name__)
            raise LeadPersistenceError("Não foi possível salvar o produto.") from exc

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
    if product is None:
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


def _product_from_row(row: dict) -> Product:
    price_type = row["tipo_preco"] if row["tipo_preco"] in PRICE_TYPES else "sob_consulta"
    return Product(
        slug=row["slug"], name=row["nome"], category=row["categoria"], description=row.get("descricao") or "",
        unit=row["unidade"], price=float(row["preco"]) if row.get("preco") is not None else None,
        price_type=price_type, available=bool(row["disponivel"]), image=row.get("imagem"),
        min_qty=int(row["qtd_min"]), max_qty=int(row["qtd_max"]), id=str(row["id"]), order=int(row.get("ordem") or 0),
    )


# ================================================================= Supabase
def get_supabase_client(settings: Settings | None = None):
    settings = settings or load_settings()
    if not settings.supabase_configured:
        raise DatabaseConfigError("SUPABASE_URL e SUPABASE_KEY não configurados. Veja o .env.example.")
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_key)


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
        return [_product_from_row(r) for r in res.data or []]

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
    def for_owner(cls, client, user_id: str) -> "SupabaseRepository":
        """Repositório da confeitaria em que o usuário logado é owner_user_id."""
        try:
            res = (client.table("confeitarias").select("slug")
                   .eq("owner_user_id", user_id).eq("ativo", True).limit(1).execute())
        except Exception as exc:
            log.error("Falha ao localizar confeitaria da usuária: %s", type(exc).__name__)
            raise LeadPersistenceError("Não foi possível carregar a confeitaria.") from exc
        if not res.data:
            raise AdminAccessError("Este usuário não está vinculado a nenhuma confeitaria.")
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
        self._write(self.client.table("produtos").insert(row), "Produto")

    def update_product(self, product_id: str, data: dict) -> None:
        store = self._require_store()
        self._write(self.client.table("produtos").update(_product_db_values(data))
                    .eq("id", product_id).eq("confeitaria_id", store.id), "Produto")


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
