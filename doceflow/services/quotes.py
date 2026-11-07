"""Solicitações de orçamento: validação, deduplicação e armazenamento.

Regras:
- Nenhuma solicitação confirma disponibilidade ou preço final.
- Coletamos só o necessário: nome, WhatsApp, produto, quantidade, data,
  retirada ou entrega e observações. Endereço, CPF e e-mail NÃO são coletados.
- `QuoteRequest.to_record()` já tem o formato da futura tabela `orcamentos`.
  Na próxima etapa, `InMemoryQuoteStore` será trocado por um repositório
  Supabase com a mesma interface (`add`).
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from services.catalog import Product, get_product

NAME_MIN, NAME_MAX = 2, 80
NOTES_MAX = 500
MAX_DAYS_AHEAD = 365
FULFILLMENT_OPTIONS = ("Retirada", "Entrega")


@dataclass
class QuoteRequest:
    customer_name: str
    whatsapp: str  # só dígitos, com DDI 55
    product_id: str
    product_name: str
    quantity: int
    unit: str
    desired_date: date
    fulfillment: str  # "Retirada" ou "Entrega"
    notes: str
    consent: bool
    status: str = "novo"
    protocol: str = field(default_factory=lambda: _new_protocol())
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def fingerprint(self) -> str:
        key = "|".join(
            [self.whatsapp, self.product_id, str(self.quantity), self.desired_date.isoformat(), self.fulfillment]
        )
        return hashlib.sha256(key.encode()).hexdigest()

    def to_record(self) -> dict:
        data = asdict(self)
        data["desired_date"] = self.desired_date.isoformat()
        data["created_at"] = self.created_at.isoformat(timespec="seconds")
        data["fingerprint"] = self.fingerprint
        return data


def _new_protocol() -> str:
    return f"DF-{datetime.now():%y%m%d}-{secrets.token_hex(2).upper()}"


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


def validate_quote(form: dict, today: date | None = None) -> tuple[QuoteRequest | None, dict[str, str]]:
    """Valida os dados do formulário. Retorna (solicitação, erros por campo)."""
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

    product: Product | None = get_product(str(form.get("product_id") or ""))
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
        QuoteRequest(
            customer_name=name,
            whatsapp=phone,
            product_id=product.id,
            product_name=product.name,
            quantity=quantity,
            unit=product.unit,
            desired_date=desired,
            fulfillment=fulfillment,
            notes=notes,
            consent=True,
        ),
        {},
    )


class DuplicateQuoteError(Exception):
    def __init__(self, existing: QuoteRequest):
        super().__init__("Solicitação duplicada")
        self.existing = existing


class InMemoryQuoteStore:
    """Armazenamento temporário (sessão do navegador). Substituído na etapa 03."""

    def __init__(self) -> None:
        self._items: dict[str, QuoteRequest] = {}

    def add(self, quote: QuoteRequest) -> QuoteRequest:
        existing = self._items.get(quote.fingerprint)
        if existing is not None:
            raise DuplicateQuoteError(existing)
        self._items[quote.fingerprint] = quote
        return quote

    def all(self) -> list[QuoteRequest]:
        return list(self._items.values())
