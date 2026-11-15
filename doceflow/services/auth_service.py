"""Autenticação da área administrativa.

- Supabase: login da proprietária pelo Supabase Auth (e-mail e senha), usando
  só a chave publishable. Os dados ficam limitados pelo RLS à confeitaria em
  que ela tem perfil ativo (admin_profiles). "Esqueci a senha" também usa o
  Supabase Auth (e-mail de recuperação + validação do token no servidor).
- SQLite (testes locais): senha ADMIN_PASSWORD.

A sessão fica ligada à configuração do servidor (nunca a parâmetros de URL) e
é revalidada a cada página administrativa. Nenhuma chave service_role é usada.
"""

import hashlib
import hmac
import logging
import re
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
    from services.supabase_client import DatabaseConfigError, get_supabase_client

    try:
        client = get_supabase_client(settings)
    except DatabaseConfigError as exc:
        # Não é senha errada: falta SUPABASE_URL/SUPABASE_KEY nos Secrets deste app. Dizer
        # "e-mail ou senha inválidos" aqui fazia a dona trocar a senha à toa.
        log.error("Login indisponível: Supabase não configurado neste app (Secrets)")
        raise AuthError("O painel ainda não está configurado para entrar (faltam os Secrets do Supabase). "
                        "Fale com o suporte do DoceFlow.") from exc
    try:
        res = client.auth.sign_in_with_password({"email": email.strip(), "password": password})
        repo = SupabaseRepository.for_owner(client, res.user.id, settings.store_slug)
    except AdminAccessError as exc:
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
        log.error("Painel bloqueado: ADMIN_PASSWORD não configurada (modo SQLite)")
        raise AuthError("O acesso ao painel ainda não foi configurado. Fale com o suporte do DoceFlow.")
    if not hmac.compare_digest(password.encode(), settings.admin_password.encode()):
        register_failure(session_state)
        raise AuthError("Senha incorreta.")
    session_state.update(admin_ok=True, admin_binding=session_token(settings), login_attempts=0)


# ------------------------------------------------------------------ esqueci a senha (Supabase)
# Fluxo: (1) a pessoa informa o e-mail; o Supabase envia um e-mail de recuperação (resposta
# sempre genérica: não revela se o e-mail existe); (2) o e-mail traz um link
# <painel>/?token_hash=...&type=recovery e/ou um código de 6 dígitos (modelo do e-mail
# configurado no Supabase: docs/implantacao/README_IMPLANTACAO.md); (3) o painel valida o token
# no servidor (verify_otp) e mostra o formulário de nova senha; (4) a senha é trocada, a sessão
# de recuperação é encerrada e a pessoa entra normalmente (o login confere o perfil de dona).
# A recuperação NUNCA abre o painel direto: trocar a senha não dá acesso a quem não é dona.
RESET_COOLDOWN = 60  # segundos entre pedidos de e-mail na mesma sessão
MIN_PASSWORD = 10
RECOVERY_KEYS = ("recovery_client", "recovery_started_at")
RECOVERY_TTL = 15 * 60  # o formulário de nova senha vale 15 min depois de validar o link
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def request_password_reset(session_state, settings, email: str) -> None:
    """Pede o e-mail de recuperação. Sucesso e "e-mail inexistente" têm a mesma resposta."""
    email = (email or "").strip().lower()
    if not _EMAIL_RE.fullmatch(email):
        raise AuthError("Informe um e-mail válido.")
    waited = time.time() - session_state.get("reset_requested_at", 0)
    if waited < RESET_COOLDOWN:
        raise AuthError(f"Aguarde {int(RESET_COOLDOWN - waited) + 1} s para pedir outro e-mail.")
    session_state["reset_requested_at"] = time.time()
    from services.supabase_client import get_supabase_client

    try:
        get_supabase_client(settings).auth.reset_password_for_email(email)
    except Exception as exc:  # o Supabase não falha para e-mail inexistente: aqui é falha real
        log.warning("Pedido de redefinição de senha falhou: %s", type(exc).__name__)
        if "rate limit" in str(exc).lower() or "429" in str(exc):
            raise AuthError("Muitos pedidos de redefinição agora. Tente de novo mais tarde.") from exc
        raise AuthError("Não foi possível enviar o e-mail agora. Tente de novo em alguns minutos.") from exc
    log.info("Pedido de redefinição de senha registrado")  # nunca registra o e-mail


def start_password_recovery(session_state, settings, *, token_hash: str | None = None,
                            email: str | None = None, code: str | None = None) -> None:
    """Valida o link (token_hash) ou o código de 6 dígitos no SERVIDOR do Supabase."""
    from services.supabase_client import get_supabase_client

    if token_hash:
        params = {"token_hash": token_hash.strip(), "type": "recovery"}
    else:
        email = (email or "").strip().lower()
        code = "".join(ch for ch in (code or "") if ch.isdigit())
        if not _EMAIL_RE.fullmatch(email) or len(code) != 6:
            raise AuthError("Informe o e-mail e o código de 6 dígitos que chegou no e-mail.")
        params = {"email": email, "token": code, "type": "recovery"}
    client = get_supabase_client(settings)
    try:
        res = client.auth.verify_otp(params)
        if getattr(res, "user", None) is None:
            raise ValueError("sem usuário")
    except Exception as exc:
        log.warning("Link ou código de recuperação recusado: %s", type(exc).__name__)
        register_failure(session_state)  # códigos errados contam para o bloqueio de tentativas
        raise AuthError("Link ou código inválido ou expirado. Peça um novo e-mail.") from exc
    logout(session_state)  # recuperação nunca convive com uma sessão administrativa
    session_state.update(recovery_client=client, recovery_started_at=time.time())


def recovery_active(session_state) -> bool:
    started = session_state.get("recovery_started_at")
    if session_state.get("recovery_client") is None or started is None:
        return False
    if time.time() - started > RECOVERY_TTL:
        cancel_password_recovery(session_state)
        return False
    return True


def complete_password_reset(session_state, password: str, confirm: str) -> None:
    if not recovery_active(session_state):
        raise AuthError("O tempo para criar a senha acabou. Peça um novo e-mail.")
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres.")
    if password != confirm:
        raise AuthError("As duas senhas não são iguais.")
    client = session_state["recovery_client"]
    try:
        client.auth.update_user({"password": password})
    except Exception as exc:
        text = str(getattr(exc, "message", "") or exc).lower()
        log.warning("Troca de senha recusada: %s", type(exc).__name__)
        if "different" in text or "same" in text:
            raise AuthError("A nova senha precisa ser diferente da anterior.") from exc
        if "weak" in text or "short" in text or "characters" in text:
            raise AuthError("Senha fraca: use letras, números e pelo menos 10 caracteres.") from exc
        raise AuthError("Não foi possível trocar a senha agora. Peça um novo e-mail.") from exc
    cancel_password_recovery(session_state)
    log.info("Senha administrativa redefinida")


def cancel_password_recovery(session_state) -> None:
    client = session_state.get("recovery_client")
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    for key in RECOVERY_KEYS:
        session_state.pop(key, None)


def require_admin(settings):
    """Guarda das páginas administrativas: devolve o repositório ou leva ao login."""
    import streamlit as st

    repo = authorized_admin_repository(st.session_state, settings)
    if repo is None:
        logout(st.session_state)
        st.switch_page(LOGIN_PAGE)
    return repo
