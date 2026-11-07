"""Integração com WhatsApp via links wa.me (sem API, sem credenciais).

O app só ABRE o WhatsApp com a mensagem pronta. Quem envia é o cliente;
por isso a interface nunca deve dizer que a mensagem "foi enviada".
"""

from __future__ import annotations

import re
from urllib.parse import quote

from services.leads import Lead


def normalize_phone(phone: str) -> str:
    """Mantém só os dígitos. Ex.: '+55 (11) 99999-9999' -> '5511999999999'."""
    return re.sub(r"\D", "", phone or "")


def build_wa_link(phone: str, message: str = "") -> str:
    """Monta o link wa.me para abrir uma conversa com mensagem pré-preenchida.

    A mensagem vai na URL (codificada em UTF-8 com quote). Não inclua dados
    sensíveis (CPF, endereço completo, dados de pagamento).
    """
    digits = normalize_phone(phone)
    if len(digits) < 10:
        raise ValueError("Número de WhatsApp inválido: informe DDI + DDD + número.")
    url = f"https://wa.me/{digits}"
    if message:
        url += f"?text={quote(message, safe='')}"
    return url


def build_lead_message(lead: Lead) -> str:
    """Mensagem montada a partir do lead GRAVADO no banco."""
    lines = [
        f"Olá, {lead.store_name}! Gostaria de um orçamento.",
        f"Pedido: {lead.protocol}",
        f"Nome: {lead.customer_name}",
        f"Produto: {lead.product_name}",
        f"Quantidade: {lead.quantity} ({lead.unit})",
        f"Data desejada: {lead.desired_date:%d/%m/%Y} ({lead.fulfillment.lower()})",
        f"Observações: {lead.notes or '-'}",
    ]
    return "\n".join(lines)


def lead_wa_link(lead: Lead) -> str | None:
    """Link para a confeitaria com a mensagem do lead, ou None se não houver número."""
    if not lead.store_whatsapp:
        return None
    return build_wa_link(lead.store_whatsapp, build_lead_message(lead))
