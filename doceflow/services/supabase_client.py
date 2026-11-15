"""Criação do cliente Supabase do DoceFlow.

Usa SOMENTE a chave publishable/anon (SUPABASE_KEY). O acesso aos dados é
limitado pelas regras de RLS do banco. Nunca use a chave service_role/secret.
"""

from __future__ import annotations

import httpx

from config import Settings, load_settings

# O padrão do SDK é esperar até 120 s e repetir as tentativas automaticamente. Com o banco fora do
# ar, a vitrine ficava 15 s (conexão recusada) ou vários minutos (servidor sem resposta) sem mostrar
# nada (QA2-04). Falhar rápido e exibir "catálogo indisponível" é melhor para a cliente.
DB_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
STORAGE_TIMEOUT_S = 20


class DatabaseConfigError(RuntimeError):
    """Configuração de banco ausente ou inválida."""


def get_supabase_client(settings: Settings | None = None):
    """Cria um cliente novo. Para o painel, use um cliente por sessão (login próprio)."""
    settings = settings or load_settings()
    if not settings.supabase_configured:
        raise DatabaseConfigError("SUPABASE_URL e SUPABASE_KEY não configurados. Veja o .env.example.")
    from supabase import ClientOptions, create_client

    # Sem novas tentativas automáticas: gravações (orçamentos e pedidos) nunca são repetidas às cegas.
    options = ClientOptions(postgrest_client_timeout=DB_TIMEOUT, postgrest_client_retry=False,
                            storage_client_timeout=STORAGE_TIMEOUT_S)
    return create_client(settings.supabase_url, settings.supabase_key, options=options)
