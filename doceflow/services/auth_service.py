"""Autenticação da área administrativa.

- Supabase: login da proprietária pelo Supabase Auth (e-mail e senha), usando
  só a chave publishable. Os dados ficam limitados pelo RLS à confeitaria em
  que ela é owner_user_id.
- SQLite (testes locais): senha ADMIN_PASSWORD.

A sessão fica ligada à configuração do servidor (nunca a parâmetros de URL) e
é revalidada a cada página administrativa. Nenhuma chave service_role é usada.
"""

import hashlib
import hmac
import logging
import secrets
import time

log = logging.getLogger("doceflow.auth")

LOGIN_PAGE = "pages/admin/login.py"
DASHBOARD_PAGE = "pages/admin/dashboard.py"
MAX_ATTEMPTS = 5
LOCK_SECONDS = 300
SESSION_KEYS = ("admin_ok", "admin_user_id", "admin_repo", "admin_binding", "admin_client")


class AuthError(Exception):
    """Login recusado. A mensagem pode ir para a tela."""


def _session_key() -> bytes:
    """Chave aleatória por processo, estável mesmo se o Streamlit recarregar este módulo
    (hot-reload em desenvolvimento), para não derrubar sessões logadas à toa."""
    try:
        import streamlit as st

        @st.cache_resource(show_spinner=False)
        def _key() -> bytes:
            return secrets.token_bytes(32)

        return _key()
    except Exception:  # fora do runtime do Streamlit (scripts, testes unitários)
        return _FALLBACK_KEY


_FALLBACK_KEY = secrets.token_bytes(32)


def session_token(settings):
    identity = '|'.join((settings.store_slug, str(settings.sqlite_path), settings.db_backend,
                         settings.supabase_url or '', settings.supabase_key or '', settings.admin_password or ''))
    return hmac.new(_session_key(), identity.encode(), hashlib.sha256).hexdigest()


def is_admin_session(session_state, settings) -> bool:
    """Verificação rápida (sem rede): usada só para decidir se o menu admin aparece.
    O acesso aos dados sempre passa por authorized_admin_repository."""
    return bool(session_state.get("admin_ok") and session_state.get("admin_binding") == session_token(settings))


def authorized_admin_repository(session_state, settings):
    """Repositório da confeitaria da sessão administrativa válida, ou None.

    Login feito, sessão ligada à configuração atual e, no Supabase, usuário
    ainda válido e dono da confeitaria.
    """
    if not is_admin_session(session_state, settings):
        return None
    from services.repository import SupabaseRepository, get_repository

    if settings.db_backend != "supabase":
        return get_repository(settings)
    try:
        client = session_state["admin_client"]
        user = client.auth.get_user().user
        if user is None or user.id != session_state.get("admin_user_id"):
            return None
        return SupabaseRepository.for_owner(client, user.id, settings.store_slug)
    except Exception:
        return None


# ------------------------------------------------------------------ login / logout
def logout(session_state) -> None:
    client = session_state.get("admin_client")
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    for key in SESSION_KEYS:
        session_state.pop(key, None)


def locked_minutes(session_state) -> int | None:
    """Minutos restantes de bloqueio após tentativas erradas, ou None."""
    locked_until = session_state.get("login_locked_until", 0)
    if time.time() < locked_until:
        return max(1, round((locked_until - time.time()) / 60))
    return None


def register_failure(session_state) -> None:
    attempts = session_state.get("login_attempts", 0) + 1
    session_state["login_attempts"] = attempts
    if attempts >= MAX_ATTEMPTS:
        session_state["login_locked_until"] = time.time() + LOCK_SECONDS
        session_state["login_attempts"] = 0


def login_supabase(session_state, settings, email: str, password: str) -> None:
    from services.repository import AdminAccessError, SupabaseRepository
    from services.supabase_client import get_supabase_client

    client = None
    try:
        client = get_supabase_client(settings)
        res = client.auth.sign_in_with_password({"email": email.strip(), "password": password})
        repo = SupabaseRepository.for_owner(client, res.user.id, settings.store_slug)
    except AdminAccessError as exc:
        if client is not None:
            client.auth.sign_out()
        raise AuthError(str(exc)) from exc
    except Exception as exc:
        log.warning("Login admin recusado: %s", type(exc).__name__)
        register_failure(session_state)
        raise AuthError("E-mail ou senha inválidos.") from exc
    session_state.update(admin_ok=True, admin_client=client, admin_user_id=res.user.id, admin_repo=repo,
                         admin_binding=session_token(settings), login_attempts=0)


def login_local(session_state, settings, password: str) -> None:
    if not settings.admin_password:
        raise AuthError("Acesso bloqueado: defina ADMIN_PASSWORD no .env para habilitar o painel.")
    if not hmac.compare_digest(password.encode(), settings.admin_password.encode()):
        register_failure(session_state)
        raise AuthError("Senha incorreta.")
    session_state.update(admin_ok=True, admin_binding=session_token(settings), login_attempts=0)


def require_admin(settings):
    """Guarda das páginas administrativas: devolve o repositório ou leva ao login."""
    import streamlit as st

    repo = authorized_admin_repository(st.session_state, settings)
    if repo is None:
        logout(st.session_state)
        st.switch_page(LOGIN_PAGE)
    return repo
