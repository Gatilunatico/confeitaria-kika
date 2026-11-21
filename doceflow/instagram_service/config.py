"""Configuração do serviço do Instagram (só variáveis de ambiente do SERVIDOR)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstagramConfig:
    app_id: str
    app_secret: str = field(repr=False)
    redirect_uri: str
    graph_version: str
    db_url: str = field(repr=False)
    supabase_url: str
    service_key: str = field(repr=False)  # Storage: só aqui, no servidor
    worker_id: str = "worker"
    scopes: tuple[str, ...] = ("instagram_business_basic", "instagram_business_content_publish")


REQUIRED = ("INSTAGRAM_APP_ID", "INSTAGRAM_APP_SECRET", "INSTAGRAM_REDIRECT_URI", "SUPABASE_DB_URL",
            "SUPABASE_URL", "SUPABASE_SERVICE_KEY")


def load_config(env: dict | None = None) -> InstagramConfig:
    env = dict(os.environ if env is None else env)
    missing = [k for k in REQUIRED if not (env.get(k) or "").strip()]
    if missing:
        raise ConfigError("Faltam variáveis do serviço do Instagram: " + ", ".join(missing))
    redirect = env["INSTAGRAM_REDIRECT_URI"].strip()
    if not redirect.startswith("https://"):
        raise ConfigError("INSTAGRAM_REDIRECT_URI precisa ser https (exigência da Meta).")
    return InstagramConfig(
        app_id=env["INSTAGRAM_APP_ID"].strip(),
        app_secret=env["INSTAGRAM_APP_SECRET"].strip(),
        redirect_uri=redirect,
        graph_version=(env.get("INSTAGRAM_GRAPH_VERSION") or "v23.0").strip(),
        db_url=env["SUPABASE_DB_URL"].strip(),
        supabase_url=env["SUPABASE_URL"].strip().rstrip("/"),
        service_key=env["SUPABASE_SERVICE_KEY"].strip(),
        worker_id=(env.get("INSTAGRAM_WORKER_ID") or f"worker-{os.getpid()}").strip()[:60],
    )
