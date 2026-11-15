"""Diagnóstico de configuração para o LOG do servidor (nunca para a tela da cliente).

Diz qual configuração parece faltar ou estar errada, sem expor valores secretos: só nomes de
variáveis e o tipo do erro. A equipe consulta no Streamlit Cloud em "Manage app → Logs".
"""

from __future__ import annotations


def config_diagnosis(settings, exc: Exception | None) -> str:
    import streamlit as st

    secrets_state = "ok"
    try:
        _ = list(st.secrets.keys())
    except Exception as secrets_exc:  # sem secrets.toml ou TOML inválido
        secrets_state = f"não lidos ({type(secrets_exc).__name__})"
    missing = [name for name, value in (("SUPABASE_URL", settings.supabase_url),
                                        ("SUPABASE_KEY", settings.supabase_key)) if not value]
    parts = [f"DB_BACKEND={settings.db_backend}", f"Secrets: {secrets_state}"]
    if settings.db_backend == "supabase":
        if missing:
            parts.append("faltando: " + ", ".join(missing))
        if settings.supabase_url and not settings.supabase_url.rstrip("/").endswith(".supabase.co"):
            parts.append("SUPABASE_URL não parece ser a URL da API (https://<id>.supabase.co)")
        if settings.supabase_key and not settings.supabase_key.startswith(("sb_publishable_", "eyJ")):
            parts.append("SUPABASE_KEY não parece ser a chave publishable/anon")
    if exc is not None:
        message = str(exc)
        for secret in (settings.supabase_key, settings.supabase_url):
            if secret:
                message = message.replace(secret, "***")
        parts.append(f"erro: {type(exc).__name__}: {message[:160]}")
    return " · ".join(parts)
