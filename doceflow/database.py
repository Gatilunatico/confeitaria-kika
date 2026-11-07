"""Camada de acesso a dados do DoceFlow.

- Produção: Supabase (PostgreSQL), configurado por variáveis de ambiente ou st.secrets.
- Testes locais: SQLite em arquivo, sem dependência externa.

As tabelas de negócio (produtos, orçamentos, oportunidades) serão definidas
nas próximas etapas. Aqui fica apenas a conexão e a checagem de saúde.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass

from config import Settings, load_settings


class DatabaseConfigError(RuntimeError):
    """Configuração de banco ausente ou inválida."""


@dataclass
class DatabaseStatus:
    backend: str
    ok: bool
    detail: str


def get_sqlite_connection(settings: Settings | None = None) -> sqlite3.Connection:
    settings = settings or load_settings()
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_supabase_client(settings: Settings | None = None):
    settings = settings or load_settings()
    if not settings.supabase_configured:
        raise DatabaseConfigError(
            "SUPABASE_URL e SUPABASE_KEY não configurados. Veja o .env.example."
        )
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_key)


def check_connection(settings: Settings | None = None) -> DatabaseStatus:
    """Testa a conexão sem expor credenciais na mensagem de retorno."""
    settings = settings or load_settings()

    if settings.db_backend == "supabase":
        try:
            get_supabase_client(settings)
            return DatabaseStatus("supabase", True, "Cliente Supabase criado.")
        except DatabaseConfigError as exc:
            return DatabaseStatus("supabase", False, str(exc))
        except Exception as exc:  # erro de biblioteca ou URL inválida
            return DatabaseStatus("supabase", False, f"Falha ao criar cliente: {type(exc).__name__}")

    if settings.db_backend == "sqlite":
        try:
            with closing(get_sqlite_connection(settings)) as conn:
                conn.execute("SELECT 1")
            return DatabaseStatus("sqlite", True, "SQLite local (somente testes).")
        except sqlite3.Error as exc:
            return DatabaseStatus("sqlite", False, f"Falha no SQLite: {exc}")

    return DatabaseStatus(settings.db_backend, False, "DB_BACKEND deve ser 'supabase' ou 'sqlite'.")
