"""Autenticação e autorização de cada pedido à API.

1. O app manda o token da sessão do Supabase (`Authorization: Bearer ...`).
2. A API cria um cliente Supabase SÓ para este pedido, com a chave publishable + esse token.
   Banco e Storage passam a responder como a usuária: o RLS decide o que ela pode ver e mudar.
3. O token é validado no Supabase Auth (`/auth/v1/user`) em todo pedido: token vencido, falso
   ou de sessão encerrada é recusado.
4. A confeitaria vem do perfil administrativo ATIVO (admin_profiles), que a usuária lê mas não
   altera. Usuário logado sem perfil recebe 403.

Nada disso depende de estado guardado na API: não há sessão, cache de token nem chave privilegiada.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from fastapi import Header

from api.errors import ApiError
from config import Settings, load_settings
from services.repository import AdminAccessError, Store, SupabaseRepository
from services.supabase_client import DB_TIMEOUT, STORAGE_TIMEOUT_S

log = logging.getLogger("doceflow.api.auth")

TOKEN_RE = re.compile(r"^[A-Za-z0-9\-_.]{20,4096}$")  # formato de um JWT (sem espaços nem quebras)
UNAUTHORIZED = {"WWW-Authenticate": "Bearer"}


@dataclass
class AdminContext:
    user_id: str
    client: object
    repo: SupabaseRepository
    store: Store
    settings: Settings


def user_client(settings: Settings, token: str):
    """Cliente Supabase com a chave publishable e o token da usuária (nunca service_role)."""
    from supabase import ClientOptions, create_client

    options = ClientOptions(headers={"Authorization": f"Bearer {token}"}, auto_refresh_token=False,
                            persist_session=False, postgrest_client_timeout=DB_TIMEOUT,
                            postgrest_client_retry=False, storage_client_timeout=STORAGE_TIMEOUT_S)
    return create_client(settings.supabase_url, settings.supabase_key, options=options)


def bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise ApiError(401, "token_ausente", "Entre no app novamente.", UNAUTHORIZED)
    scheme, _, token = authorization.partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not TOKEN_RE.match(token):
        raise ApiError(401, "token_invalido", "Sessão inválida. Entre no app novamente.", UNAUTHORIZED)
    return token


def resolve_admin(authorization: str | None, settings: Settings | None = None, make_client=None) -> AdminContext:
    token = bearer_token(authorization)
    settings = settings or load_settings()
    if settings.db_backend != "supabase" or not settings.supabase_configured:
        log.error("API sem Supabase configurado (SUPABASE_URL/SUPABASE_KEY)")
        raise ApiError(503, "servico_indisponivel", "Serviço indisponível no momento.")
    client = (make_client or user_client)(settings, token)
    try:
        user = client.auth.get_user(token)
        user_id = str(user.user.id) if user and user.user else None
    except Exception as exc:
        log.info("Token recusado pelo Supabase Auth: %s", type(exc).__name__)
        user_id = None
    if not user_id:
        raise ApiError(401, "token_invalido", "Sessão expirada. Entre no app novamente.", UNAUTHORIZED)
    try:
        repo = SupabaseRepository.for_owner(client, user_id, settings.store_slug)
        store = repo.get_store()
    except AdminAccessError as exc:
        raise ApiError(403, "sem_permissao", "Esta conta não administra a confeitaria.") from exc
    except Exception as exc:
        log.error("Falha ao carregar a confeitaria da usuária: %s", type(exc).__name__)
        raise ApiError(503, "servico_indisponivel", "Serviço indisponível no momento.") from exc
    if store is None:
        raise ApiError(403, "sem_permissao", "Esta conta não administra a confeitaria.")
    return AdminContext(user_id=user_id, client=client, repo=repo, store=store, settings=settings)


def require_admin(authorization: str | None = Header(default=None)) -> AdminContext:
    """Dependência do FastAPI: toda rota administrativa passa por aqui."""
    return resolve_admin(authorization)
