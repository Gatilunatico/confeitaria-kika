"""Authentication binding invalidates sessions when tenant, database or password changes."""
import hashlib
import hmac
from config import get_setting


def session_token(settings):
    if not settings.admin_password:
        return None
    identity = f'{get_setting("STORE_ID", "kika-cakes")}|{settings.sqlite_path}|{settings.db_backend}'
    return hmac.new(settings.admin_password.encode(), identity.encode(), hashlib.sha256).hexdigest()


def authenticate(password, settings):
    return bool(settings.admin_password and hmac.compare_digest(password.encode(), settings.admin_password.encode()))
