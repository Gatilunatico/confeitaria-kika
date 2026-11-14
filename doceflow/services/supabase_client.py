"""Criação do cliente Supabase do DoceFlow.

Usa SOMENTE a chave publishable/anon (SUPABASE_KEY). O acesso aos dados é
limitado pelas regras de RLS do banco. Nunca use a chave service_role/secret.
"""

from __future__ import annotations

from config import Settings, load_settings


class DatabaseConfigError(RuntimeError):
    """Configuração de banco ausente ou inválida."""


def get_supabase_client(settings: Settings | None = None):
    """Cria um cliente novo. Para o painel, use um cliente por sessão (login próprio)."""
    settings = settings or load_settings()
    if not settings.supabase_configured:
        raise DatabaseConfigError("SUPABASE_URL e SUPABASE_KEY não configurados. Veja o .env.example.")
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_key)
