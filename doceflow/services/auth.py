"""Bind administrative sessions to server configuration, never to URL parameters."""
import hashlib
import hmac
import secrets

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


def authorized_admin_repository(session_state, settings):
    """Repositório da confeitaria da sessão administrativa válida, ou None.

    Mesma regra do painel: login feito, sessão ligada à configuração atual e,
    no Supabase, usuário ainda válido e dono da confeitaria.
    """
    if not (session_state.get("admin_ok") and session_state.get("admin_binding") == session_token(settings)):
        return None
    from database import SupabaseRepository, get_repository

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
