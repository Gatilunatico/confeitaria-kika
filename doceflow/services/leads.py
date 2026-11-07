"""Leads (solicitações de orçamento): validação e modelos.

Regras:
- Nenhuma solicitação confirma disponibilidade ou preço final.
- Coleta mínima: nome, WhatsApp, produto, quantidade, data, retirada ou
  entrega e observações. Endereço, CPF e e-mail NÃO são coletados.
- A validação daqui serve para a experiência do usuário. O banco valida de
  novo (constraints + função `criar_lead`), porque é a barreira de segurança.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, timedelta

from services.catalog import Product, find_product

NAME_MIN, NAME_MAX = 2, 80
NOTES_MAX = 500
MAX_DAYS_AHEAD = 365
FULFILLMENT_OPTIONS = ("Retirada", "Entrega")
STATUS_NEW = "Novo"
DEFAULT_ORIGIN = "site"


class LeadValidationError(ValueError):
    """Dados recusados (pelo app ou pelo banco). A mensagem pode ir para a tela."""


class LeadPersistenceError(RuntimeError):
    """Falha de infraestrutura ao gravar. Nunca exibir detalhes técnicos na tela."""


@dataclass(frozen=True)
class LeadRequest:
    """Dados validados, prontos para gravar."""

    customer_name: str
    whatsapp: str  # só dígitos, com DDI 55
    product_slug: str
    quantity: int
    desired_date: date
    fulfillment: str
    notes: str
    consent: bool
    origin: str = DEFAULT_ORIGIN


@dataclass(frozen=True)
class Lead:
    """Lead como gravado no banco (fonte da mensagem do WhatsApp)."""

    id: str
    protocol: str
    created: bool  # False = pedido idêntico já existia (não duplicou)
    product_name: str
    unit: str
    quantity: int
    desired_date: date
    fulfillment: str
    notes: str
    customer_name: str
    status: str
    store_name: str
    store_whatsapp: str | None


# Mensagens amigáveis para os códigos levantados pela função criar_lead.
DB_ERROR_MESSAGES = {
    "confeitaria_invalida": "Esta vitrine está indisponível no momento.",
    "produto_invalido": "Produto não encontrado. Escolha um produto do catálogo.",
    "produto_indisponivel": "Este produto ficou indisponível. Escolha outro produto.",
    "quantidade_invalida": "Quantidade fora do permitido para este produto.",
    "data_invalida": "Data inválida. Escolha uma data a partir de hoje, dentro de 12 meses.",
    "consentimento_obrigatorio": "É preciso concordar com o uso dos dados para o contato sobre o orçamento.",
}


def lead_fingerprint(whatsapp: str, product_id: str, quantity: int, desired: date, fulfillment: str) -> str:
    """Mesma fórmula da função SQL criar_lead: md5(whatsapp|produto_id|qtd|data|modalidade)."""
    key = "|".join([whatsapp, product_id, str(quantity), desired.isoformat(), fulfillment])
    return hashlib.md5(key.encode()).hexdigest()  # noqa: S324 - deduplicação, não segurança


def normalize_br_whatsapp(raw: str) -> str | None:
    """Retorna o número com DDI 55 (só dígitos) ou None se inválido.

    Aceita celular (DDD + 9 dígitos começando com 9) e fixo
    (DDD + 8 dígitos começando com 2 a 5), com ou sem +55.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) not in (10, 11):
        return None
    ddd, number = digits[:2], digits[2:]
    if "0" in ddd:
        return None
    if len(number) == 9 and number[0] != "9":
        return None
    if len(number) == 8 and number[0] not in "2345":
        return None
    if len(set(number)) == 1:
        return None
    return "55" + digits


def format_br_phone(e164_digits: str) -> str:
    local = e164_digits[2:]
    ddd, number = local[:2], local[2:]
    return f"({ddd}) {number[:-4]}-{number[-4:]}"


def normalize_origin(raw: str | None) -> str:
    """Origem da visita (ex.: ?origem=instagram ou ?utm_source=instagram)."""
    value = re.sub(r"[^a-z0-9_-]", "", (raw or "").strip().lower())[:40]
    return value or DEFAULT_ORIGIN


def validate_lead(
    form: dict, products: list[Product], today: date | None = None
) -> tuple[LeadRequest | None, dict[str, str]]:
    """Valida os dados do formulário. Retorna (pedido, erros por campo)."""
    today = today or date.today()
    errors: dict[str, str] = {}

    name = " ".join(str(form.get("customer_name") or "").split())
    if not name:
        errors["customer_name"] = "Informe seu nome."
    elif not (NAME_MIN <= len(name) <= NAME_MAX) or not re.search(r"[A-Za-zÀ-ÿ]", name):
        errors["customer_name"] = f"Nome deve ter entre {NAME_MIN} e {NAME_MAX} letras."

    raw_phone = str(form.get("whatsapp") or "").strip()
    phone = normalize_br_whatsapp(raw_phone)
    if not raw_phone:
        errors["whatsapp"] = "Informe seu WhatsApp com DDD."
    elif phone is None:
        errors["whatsapp"] = "WhatsApp inválido. Use DDD + número, ex.: (11) 99999-9999."

    product = find_product(products, str(form.get("product_id") or ""))
    if product is None:
        errors["product_id"] = "Escolha um produto do catálogo."
    elif not product.available:
        errors["product_id"] = f"{product.name} está indisponível no momento. Escolha outro produto."

    quantity = form.get("quantity")
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        quantity = None
    if quantity is None:
        errors["quantity"] = "Informe a quantidade."
    elif product is not None and not (product.min_qty <= quantity <= product.max_qty):
        errors["quantity"] = f"Quantidade deve ser entre {product.min_qty} e {product.max_qty} ({product.unit})."
    elif product is None and quantity < 1:
        errors["quantity"] = "Quantidade deve ser maior que zero."

    desired = form.get("desired_date")
    if not isinstance(desired, date):
        errors["desired_date"] = "Informe a data desejada."
    elif desired < today:
        errors["desired_date"] = "A data não pode estar no passado."
    elif desired > today + timedelta(days=MAX_DAYS_AHEAD):
        errors["desired_date"] = "Escolha uma data dentro dos próximos 12 meses."

    fulfillment = form.get("fulfillment")
    if fulfillment not in FULFILLMENT_OPTIONS:
        errors["fulfillment"] = "Escolha retirada ou entrega."

    notes = str(form.get("notes") or "").strip()
    if len(notes) > NOTES_MAX:
        errors["notes"] = f"Observações devem ter no máximo {NOTES_MAX} caracteres."

    if not form.get("consent"):
        errors["consent"] = "É preciso concordar com o uso dos dados para o contato sobre o orçamento."

    if errors:
        return None, errors

    return (
        LeadRequest(
            customer_name=name,
            whatsapp=phone,
            product_slug=product.slug,
            quantity=quantity,
            desired_date=desired,
            fulfillment=fulfillment,
            notes=notes,
            consent=True,
            origin=normalize_origin(form.get("origin")),
        ),
        {},
    )
