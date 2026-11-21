"""Acesso do serviço ao banco (funções da migração 014) e ao Storage (só no servidor)."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO

import httpx
import psycopg
from psycopg.rows import dict_row
from PIL import Image

log = logging.getLogger("doceflow.instagram.store")


@dataclass
class Publication:
    id: str
    confeitaria_id: str
    formato: str
    legenda: str
    imagem_path: str
    tentativas: int
    max_tentativas: int
    ig_container_id: str | None
    bloqueado_em: datetime | None

    @classmethod
    def from_row(cls, r: dict) -> "Publication":
        return cls(id=str(r["id"]), confeitaria_id=str(r["confeitaria_id"]), formato=r["formato"],
                   legenda=r["legenda"] or "", imagem_path=r["imagem_path"], tentativas=int(r["tentativas"]),
                   max_tentativas=int(r["max_tentativas"]), ig_container_id=r["ig_container_id"],
                   bloqueado_em=r["bloqueado_em"])


def hash_state(nonce: str) -> str:
    return hashlib.sha256(nonce.encode()).hexdigest()


class Database:
    """Cada operação numa transação própria (funciona com o pooler de transações do Supabase)."""

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _run(self, sql: str, params=(), fetch: str = "none"):
        with psycopg.connect(self.dsn, autocommit=False, prepare_threshold=None, row_factory=dict_row) as conn:
            with conn.transaction():
                cur = conn.execute(sql, params)
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return cur.fetchall()
                return None

    # OAuth
    def create_state(self, nonce: str, store_id: str, user_id: str, ttl: timedelta) -> None:
        self._run("select public.instagram_criar_estado(%s, %s, %s, %s)", (hash_state(nonce), store_id, user_id, ttl))

    def consume_state(self, nonce: str) -> tuple[str, str] | None:
        row = self._run("select * from public.instagram_consumir_estado(%s)", (hash_state(nonce),), "one")
        return (str(row["confeitaria_id"]), str(row["user_id"])) if row else None

    def save_connection(self, store_id: str, ig_user_id: str, username: str, account_type: str, token: str,
                        expires_at: datetime | None) -> None:
        self._run("select public.instagram_salvar_conexao(%s, %s, %s, %s, %s, %s)",
                  (store_id, ig_user_id, username, account_type, token, expires_at))

    def token(self, store_id: str) -> tuple[str, str, datetime | None] | None:
        row = self._run("select * from public.instagram_token(%s)", (store_id,), "one")
        return (row["ig_user_id"], row["token"], row["expira_em"]) if row else None

    def accounts_to_refresh(self, before: timedelta) -> list[str]:
        return [str(r["confeitaria_id"]) for r in
                self._run("select * from public.instagram_contas_para_renovar(%s)", (before,), "all")]

    def account_error(self, store_id: str, message: str) -> None:
        self._run("select public.instagram_marcar_conta_erro(%s, %s)", (store_id, message))

    # Fila
    def reserve(self, worker: str, limit: int = 5) -> list[Publication]:
        rows = self._run("select * from public.instagram_reservar_publicacoes(%s, %s)", (worker, limit), "all")
        return [Publication.from_row(r) for r in rows]

    def save_container(self, pub_id: str, container_id: str) -> None:
        self._run("select public.instagram_salvar_container(%s, %s)", (pub_id, container_id))

    def conclude(self, pub_id: str, media_id: str, permalink: str | None) -> None:
        self._run("select public.instagram_concluir_publicacao(%s, %s, %s)", (pub_id, media_id, permalink))

    def fail(self, pub_id: str, code: str, message: str, temporary: bool, wait: timedelta) -> str:
        row = self._run("select public.instagram_registrar_falha(%s, %s, %s, %s, %s) as status",
                        (pub_id, code, message, temporary, wait), "one")
        return row["status"]

    def mark_verify(self, pub_id: str, message: str) -> None:
        self._run("select public.instagram_marcar_verificar(%s, %s)", (pub_id, message))

    def log(self, pub_id: str, event: str, detail: str | None = None) -> None:
        self._run("select public.instagram_log(%s, %s, %s)", (pub_id, event, detail))


class Storage:
    """Lê o PNG do post (bucket privado marketing), grava o JPEG para a Meta (instagram-media) e
    gera um link assinado temporário. Usa a chave de serviço, que existe só neste servidor."""

    SOURCE, TARGET = "marketing", "instagram-media"

    def __init__(self, supabase_url: str, service_key: str, client: httpx.Client | None = None, link_ttl: int = 3600):
        self.base = supabase_url.rstrip("/") + "/storage/v1"
        self._key = service_key
        self.http = client or httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
        self.link_ttl = link_ttl

    def _headers(self) -> dict:
        h = {"apikey": self._key}
        if not self._key.startswith("sb_secret_"):
            h["Authorization"] = f"Bearer {self._key}"  # chave antiga (JWT service_role)
        return h

    def jpeg_url(self, store_id: str, pub_id: str, png_path: str) -> str:
        if not png_path.startswith(f"{store_id}/"):
            raise ValueError("imagem de outra confeitaria")
        resp = self.http.get(f"{self.base}/object/{self.SOURCE}/{png_path}", headers=self._headers())
        resp.raise_for_status()
        jpeg = to_jpeg(resp.content)
        target = f"{store_id}/{pub_id}.jpg"
        up = self.http.post(f"{self.base}/object/{self.TARGET}/{target}", content=jpeg,
                            headers={**self._headers(), "content-type": "image/jpeg", "x-upsert": "true"})
        up.raise_for_status()
        sign = self.http.post(f"{self.base}/object/sign/{self.TARGET}/{target}", json={"expiresIn": self.link_ttl},
                              headers=self._headers())
        sign.raise_for_status()
        signed = sign.json().get("signedURL") or sign.json().get("signedUrl")
        if not signed:
            raise RuntimeError("Storage não devolveu o link assinado")
        return signed if signed.startswith("http") else f"{self.base}{signed}"


def to_jpeg(png: bytes) -> bytes:
    """A Meta só aceita JPEG. Converte sem metadados, sobre fundo branco se houver transparência."""
    img = Image.open(BytesIO(png))
    img.load()
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    out = BytesIO()
    img.save(out, format="JPEG", quality=92, optimize=True)
    return out.getvalue()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
