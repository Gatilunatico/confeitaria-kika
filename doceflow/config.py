"""Configuração central do DoceFlow.

Ordem de leitura de cada variável:
1. st.secrets (Streamlit Cloud ou .streamlit/secrets.toml local)
2. variáveis de ambiente (incluindo o arquivo .env carregado pelo python-dotenv)
3. valor padrão

Nenhuma credencial fica no código. Os valores sensíveis nunca devem ser
impressos em logs nem exibidos na interface.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _from_streamlit_secrets(name: str) -> str | None:
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        # Sem secrets.toml ou fora do contexto do Streamlit.
        pass
    return None


def get_setting(name: str, default: str | None = None) -> str | None:
    value = _from_streamlit_secrets(name)
    if value is None:
        value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


@dataclass(frozen=True)
class Settings:
    app_name: str
    store_name: str
    store_slug: str
    db_backend: str  # "supabase" ou "sqlite"
    supabase_url: str | None
    supabase_key: str | None
    sqlite_path: Path
    whatsapp_number: str | None
    admin_password: str | None

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


def load_settings() -> Settings:
    sqlite_path = Path(get_setting("SQLITE_PATH", "data/doceflow_dev.db"))
    if not sqlite_path.is_absolute():
        sqlite_path = BASE_DIR / sqlite_path
    return Settings(
        app_name=get_setting("APP_NAME", "DoceFlow"),
        store_name=get_setting("STORE_NAME", "Kika Cakes"),
        store_slug=get_setting("STORE_SLUG", "kika-cakes"),
        db_backend=(get_setting("DB_BACKEND", "sqlite") or "sqlite").lower(),
        supabase_url=get_setting("SUPABASE_URL"),
        supabase_key=get_setting("SUPABASE_KEY"),
        sqlite_path=sqlite_path,
        whatsapp_number=get_setting("WHATSAPP_NUMBER"),
        admin_password=get_setting("ADMIN_PASSWORD"),
    )
