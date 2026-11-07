"""Bind administrative sessions to server configuration, never to URL parameters."""
import hashlib
import hmac
import secrets

_SESSION_KEY = secrets.token_bytes(32)


def session_token(settings):
    identity = '|'.join((settings.store_slug, str(settings.sqlite_path), settings.db_backend,
                         settings.supabase_url or '', settings.supabase_key or '', settings.admin_password or ''))
    return hmac.new(_SESSION_KEY, identity.encode(), hashlib.sha256).hexdigest()
