"""Persistência dos posts do Estúdio de Marketing.

- Supabase: tabela `marketing_posts` + imagens no bucket PRIVADO `marketing`
  (caminho <confeitaria_id>/<post_id>.png). Usa o cliente logado da dona; o
  RLS garante que cada confeitaria só acessa os próprios posts e imagens.
- SQLite (testes locais): tabela equivalente + PNGs em data/marketing/.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone

from config import Settings
from services.repository import get_sqlite_connection

log = logging.getLogger("doceflow.marketing")

MARKETING_STATUSES = ("Rascunho", "Pronto", "Publicado manualmente")
BUCKET = "marketing"
MAX_PNG_BYTES = 5 * 1024 * 1024
LIMITS = {"titulo": 120, "preco_texto": 80, "cta": 60, "legenda": 2200, "produto_nome": 120}

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS marketing_posts (
    id TEXT PRIMARY KEY,
    confeitaria_id TEXT NOT NULL REFERENCES confeitarias(id) ON DELETE CASCADE,
    produto_id TEXT REFERENCES produtos(id) ON DELETE SET NULL,
    produto_nome TEXT NOT NULL,
    template TEXT NOT NULL CHECK (template IN ('produto','promocao','novidade')),
    formato TEXT NOT NULL CHECK (formato IN ('feed','story')),
    titulo TEXT NOT NULL DEFAULT '', preco_texto TEXT NOT NULL DEFAULT '', cta TEXT NOT NULL DEFAULT '',
    tom TEXT NOT NULL CHECK (tom IN ('amigavel','promocional','elegante')),
    legenda TEXT NOT NULL DEFAULT '',
    imagem_path TEXT,
    status TEXT NOT NULL DEFAULT 'Rascunho' CHECK (status IN ('Rascunho','Pronto','Publicado manualmente')),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""
COLUMNS = ("id", "produto_id", "produto_nome", "template", "formato", "titulo", "preco_texto", "cta", "tom",
           "legenda", "imagem_path", "status", "created_at", "updated_at")


class MarketingError(RuntimeError):
    """Falha ao salvar/carregar posts. A mensagem pode ir para a tela."""


class DuplicatePostError(MarketingError):
    """Já existe um post com este id (pedido repetido: o post original foi mantido)."""


@dataclass
class PostDraft:
    produto_id: str | None
    produto_nome: str
    template: str
    formato: str
    titulo: str
    preco_texto: str
    cta: str
    tom: str
    legenda: str
    status: str = "Rascunho"

    def validate(self) -> None:
        if self.status not in MARKETING_STATUSES:
            raise MarketingError("Status inválido.")
        for field, limit in LIMITS.items():
            if len(getattr(self, field) or "") > limit:
                raise MarketingError(f"O campo {field.replace('_', ' ')} passa de {limit} caracteres.")

    def row(self) -> dict:
        self.validate()
        return {k: getattr(self, k) for k in ("produto_id", "produto_nome", "template", "formato", "titulo",
                                               "preco_texto", "cta", "tom", "legenda", "status")}


def _check_png(png: bytes) -> None:
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise MarketingError("A imagem gerada não é um PNG válido.")
    if len(png) > MAX_PNG_BYTES:
        raise MarketingError("A imagem passa de 5 MB.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ================================================================ SQLite
class SQLiteMarketingStore:
    backend = "sqlite"

    def __init__(self, settings: Settings, store_id: str):
        self.settings, self.store_id = settings, store_id
        self.images_dir = settings.sqlite_path.parent / "marketing" / store_id
        self.images_dir.mkdir(parents=True, exist_ok=True)
        with closing(get_sqlite_connection(settings)) as conn, conn:
            conn.executescript(SQLITE_SCHEMA)

    def _write_png(self, post_id: str, png: bytes) -> str:
        _check_png(png)
        (self.images_dir / f"{post_id}.png").write_bytes(png)
        return f"{self.store_id}/{post_id}.png"

    def save(self, draft: PostDraft, png: bytes, post_id: str | None = None) -> str:
        row = draft.row()
        if post_id is not None and self.get(post_id) is not None:
            raise DuplicatePostError("Este post já foi salvo.")
        post_id, now = post_id or str(uuid.uuid4()), _now()
        path = self._write_png(post_id, png)
        with closing(get_sqlite_connection(self.settings)) as conn, conn:
            conn.execute(
                f"INSERT INTO marketing_posts (id, confeitaria_id, {', '.join(row)}, imagem_path, created_at, updated_at)"
                f" VALUES (?, ?, {', '.join('?' for _ in row)}, ?, ?, ?)",
                (post_id, self.store_id, *row.values(), path, now, now),
            )
        return post_id

    def update(self, post_id: str, draft: PostDraft, png: bytes | None = None) -> None:
        row = draft.row()
        if png is not None:
            self._write_png(post_id, png)
        with closing(get_sqlite_connection(self.settings)) as conn, conn:
            cur = conn.execute(
                f"UPDATE marketing_posts SET {', '.join(f'{k} = ?' for k in row)}, updated_at = ?"
                " WHERE id = ? AND confeitaria_id = ?",
                (*row.values(), _now(), post_id, self.store_id),
            )
        if cur.rowcount != 1:
            raise MarketingError("Post não encontrado.")

    def set_status(self, post_id: str, status: str) -> None:
        if status not in MARKETING_STATUSES:
            raise MarketingError("Status inválido.")
        with closing(get_sqlite_connection(self.settings)) as conn, conn:
            cur = conn.execute("UPDATE marketing_posts SET status = ?, updated_at = ? WHERE id = ? AND confeitaria_id = ?",
                               (status, _now(), post_id, self.store_id))
        if cur.rowcount != 1:
            raise MarketingError("Post não encontrado.")

    def get(self, post_id: str) -> dict | None:
        with closing(get_sqlite_connection(self.settings)) as conn:
            row = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM marketing_posts WHERE id = ? AND confeitaria_id = ?",
                               (post_id, self.store_id)).fetchone()
        return dict(row) if row else None

    def list(self) -> list[dict]:
        with closing(get_sqlite_connection(self.settings)) as conn:
            rows = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM marketing_posts WHERE confeitaria_id = ?"
                                " ORDER BY created_at DESC", (self.store_id,)).fetchall()
        return [dict(r) for r in rows]

    def image(self, path: str) -> bytes:
        store, name = path.split("/", 1)
        if store != self.store_id or "/" in name or ".." in name:
            raise MarketingError("Imagem não encontrada.")
        file = self.images_dir / name
        if not file.exists():
            raise MarketingError("Imagem não encontrada.")
        return file.read_bytes()


# ================================================================ Supabase
def _translate(exc: Exception) -> MarketingError:
    text = str(getattr(exc, "message", "") or exc)
    code = str(getattr(exc, "code", "") or "")
    if code in {"42P01", "PGRST205"} or "marketing_posts" in text and "not find" in text.lower() \
            or "Bucket not found" in text:
        return MarketingError("O módulo de marketing ainda não foi ativado no banco "
                              "(rode a migração 004_marketing.sql no Supabase).")
    if code == "42501" or "row-level security" in text.lower() or "Unauthorized" in text:
        return MarketingError("Sem permissão para salvar. Entre novamente no painel.")
    log.error("Falha no marketing (supabase): %s %s", type(exc).__name__, code)
    return MarketingError("Não foi possível salvar agora. Tente novamente.")


class SupabaseMarketingStore:
    backend = "supabase"

    def __init__(self, client, store_id: str):
        self.client, self.store_id = client, store_id

    def _upload(self, path: str, png: bytes) -> None:
        _check_png(png)
        self.client.storage.from_(BUCKET).upload(path, png, {"content-type": "image/png", "upsert": "true"})

    def save(self, draft: PostDraft, png: bytes, post_id: str | None = None) -> str:
        """post_id opcional: o app manda um id fixo por toque, e repetir o pedido não duplica o post."""
        row = draft.row()
        if post_id is not None and self.get(post_id) is not None:
            raise DuplicatePostError("Este post já foi salvo.")
        post_id = post_id or str(uuid.uuid4())
        path = f"{self.store_id}/{post_id}.png"
        try:
            self._upload(path, png)
        except MarketingError:
            raise
        except Exception as exc:
            raise _translate(exc) from exc
        try:
            res = self.client.table("marketing_posts").insert(
                {"id": post_id, "confeitaria_id": self.store_id, "imagem_path": path, **row}).execute()
            if not res.data:
                raise MarketingError("O banco não confirmou o salvamento.")
        except Exception as exc:
            if str(getattr(exc, "code", "") or "") == "23505":  # mesmo id salvo por outro pedido: mantém a imagem
                raise DuplicatePostError("Este post já foi salvo.") from exc
            try:  # não deixa imagem órfã no Storage
                self.client.storage.from_(BUCKET).remove([path])
            except Exception:
                pass
            if isinstance(exc, MarketingError):
                raise
            raise _translate(exc) from exc
        return post_id

    def update(self, post_id: str, draft: PostDraft, png: bytes | None = None) -> None:
        row = draft.row()
        try:
            if png is not None:
                self._upload(f"{self.store_id}/{post_id}.png", png)
            res = (self.client.table("marketing_posts").update(row)
                   .eq("id", post_id).eq("confeitaria_id", self.store_id).execute())
        except MarketingError:
            raise
        except Exception as exc:
            raise _translate(exc) from exc
        if not res.data:
            raise MarketingError("Post não encontrado.")

    def set_status(self, post_id: str, status: str) -> None:
        if status not in MARKETING_STATUSES:
            raise MarketingError("Status inválido.")
        try:
            res = (self.client.table("marketing_posts").update({"status": status})
                   .eq("id", post_id).eq("confeitaria_id", self.store_id).execute())
        except Exception as exc:
            raise _translate(exc) from exc
        if not res.data:
            raise MarketingError("Post não encontrado.")

    def get(self, post_id: str) -> dict | None:
        try:
            res = (self.client.table("marketing_posts").select(",".join(COLUMNS))
                   .eq("id", post_id).eq("confeitaria_id", self.store_id).limit(1).execute())
        except Exception as exc:
            raise _translate(exc) from exc
        return res.data[0] if res.data else None

    def list(self) -> list[dict]:
        try:
            res = (self.client.table("marketing_posts").select(",".join(COLUMNS))
                   .eq("confeitaria_id", self.store_id).order("created_at", desc=True).execute())
        except Exception as exc:
            raise _translate(exc) from exc
        return res.data or []

    def image(self, path: str) -> bytes:
        if not path.startswith(f"{self.store_id}/"):
            raise MarketingError("Imagem não encontrada.")
        try:
            return self.client.storage.from_(BUCKET).download(path)
        except Exception as exc:
            raise _translate(exc) from exc


def get_marketing_store(settings: Settings, repo):
    """Store da confeitaria do repositório (no Supabase, o repositório logado da dona)."""
    store = repo.get_store()
    if store is None:
        raise MarketingError("Confeitaria não encontrada.")
    if settings.db_backend == "supabase":
        return SupabaseMarketingStore(repo.client, store.id)
    return SQLiteMarketingStore(settings, store.id)
