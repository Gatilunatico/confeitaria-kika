"""Integração com WhatsApp via links wa.me (sem API, sem credenciais)."""

from __future__ import annotations

import re
from urllib.parse import quote


def normalize_phone(phone: str) -> str:
    """Mantém só os dígitos. Ex.: '+55 (11) 99999-9999' -> '5511999999999'."""
    return re.sub(r"\D", "", phone or "")


def build_wa_link(phone: str, message: str = "") -> str:
    """Monta o link wa.me para abrir uma conversa com mensagem pré-preenchida.

    Atenção: a mensagem vai na URL. Não inclua dados sensíveis
    (CPF, endereço completo, dados de pagamento).
    """
    digits = normalize_phone(phone)
    if len(digits) < 10:
        raise ValueError("Número de WhatsApp inválido: informe DDI + DDD + número.")
    url = f"https://wa.me/{digits}"
    if message:
        url += f"?text={quote(message)}"
    return url
