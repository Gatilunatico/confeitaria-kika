"""Pedidos: validação no app e modelos (o banco valida de novo em criar_pedido).

Fluxo público: o visitante envia itens e dados de contato; a função criar_pedido do
banco grava o pedido e os itens sem dar ao visitante acesso de leitura às tabelas.
Fluxo administrativo: a dona consulta e atualiza os pedidos da própria confeitaria
(status, valor final, data de entrega e observações internas), garantido pelo RLS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from services.product_service import Product, find_product
from services.quote_service import (
    FULFILLMENT_OPTIONS,
    MAX_DAYS_AHEAD,
    NAME_MAX,
    NAME_MIN,
    NOTES_MAX,
    normalize_br_whatsapp,
    normalize_origin,
)

ORDER_STATUSES = ("Recebido", "Confirmado", "Em produção", "Pronto", "Entregue", "Cancelado")
ADMIN_EDITABLE = ("status", "valor_final", "data_entrega", "observacoes_internas")
MAX_ITEMS = 20


@dataclass(frozen=True)
class OrderItemRequest:
    product_slug: str
    quantity: int


@dataclass(frozen=True)
class OrderRequest:
    customer_name: str
    whatsapp: str
    delivery_date: date
    fulfillment: str
    notes: str
    items: tuple[OrderItemRequest, ...]
    consent: bool
    origin: str = "site"

    def rpc_items(self) -> list[dict]:
        return [{"produto_slug": i.product_slug, "quantidade": i.quantity} for i in self.items]


@dataclass(frozen=True)
class Order:
    id: str
    protocol: str
    created: bool
    status: str
    estimated_total: float | None
    store_name: str
    store_whatsapp: str | None
    items: list[dict] = field(default_factory=list)


def validate_order(form: dict, products: list[Product], today: date | None = None
                   ) -> tuple[OrderRequest | None, dict[str, str]]:
    """Valida o pedido. form["items"] = [{"product_id": slug, "quantity": n}, ...]."""
    today = today or date.today()
    errors: dict[str, str] = {}
    name = " ".join(str(form.get("customer_name") or "").split())
    if not (NAME_MIN <= len(name) <= NAME_MAX):
        errors["customer_name"] = f"Nome deve ter entre {NAME_MIN} e {NAME_MAX} letras."
    phone = normalize_br_whatsapp(str(form.get("whatsapp") or ""))
    if phone is None:
        errors["whatsapp"] = "WhatsApp inválido. Use DDD + número, ex.: (11) 99999-9999."
    delivery = form.get("delivery_date")
    if not isinstance(delivery, date) or not (today <= delivery <= today + timedelta(days=MAX_DAYS_AHEAD)):
        errors["delivery_date"] = "Escolha uma data a partir de hoje, dentro de 12 meses."
    if form.get("fulfillment") not in FULFILLMENT_OPTIONS:
        errors["fulfillment"] = "Escolha retirada ou entrega."
    notes = str(form.get("notes") or "").strip()
    if len(notes) > NOTES_MAX:
        errors["notes"] = f"Observações devem ter no máximo {NOTES_MAX} caracteres."
    if not form.get("consent"):
        errors["consent"] = "É preciso concordar com o uso dos dados para o contato sobre o pedido."

    raw_items = form.get("items") or []
    items: list[OrderItemRequest] = []
    if not 1 <= len(raw_items) <= MAX_ITEMS:
        errors["items"] = f"O pedido precisa ter de 1 a {MAX_ITEMS} produtos."
    seen: set[str] = set()
    for raw in raw_items:
        slug = str(raw.get("product_id") or "")
        product = find_product(products, slug)
        try:
            qty = int(raw.get("quantity"))
        except (TypeError, ValueError):
            qty = 0
        if product is None or not product.published:
            errors["items"] = "Um dos produtos não está no catálogo."
        elif not product.available:
            errors["items"] = f"{product.name} está indisponível no momento."
        elif not product.min_qty <= qty <= product.max_qty:
            errors["items"] = f"{product.name}: quantidade entre {product.min_qty} e {product.max_qty} ({product.unit})."
        elif slug in seen:
            errors["items"] = f"{product.name} aparece mais de uma vez: ajuste a quantidade."
        else:
            seen.add(slug)
            items.append(OrderItemRequest(slug, qty))
    if errors:
        return None, errors
    return OrderRequest(customer_name=name, whatsapp=phone, delivery_date=delivery, fulfillment=form["fulfillment"],
                        notes=notes, items=tuple(items), consent=True,
                        origin=normalize_origin(form.get("origin"))), {}


def validate_order_update(fields: dict) -> dict:
    """Só os campos que a administradora pode alterar (o banco também restringe por coluna)."""
    unknown = set(fields) - set(ADMIN_EDITABLE)
    if unknown:
        raise ValueError(f"Campos não editáveis: {', '.join(sorted(unknown))}")
    if "status" in fields and fields["status"] not in ORDER_STATUSES:
        raise ValueError("Status de pedido inválido.")
    if fields.get("valor_final") is not None and float(fields["valor_final"]) < 0:
        raise ValueError("O valor final não pode ser negativo.")
    if "observacoes_internas" in fields and len(str(fields["observacoes_internas"])) > 1000:
        raise ValueError("Observações internas: no máximo 1000 caracteres.")
    clean = dict(fields)
    if isinstance(clean.get("data_entrega"), date):
        clean["data_entrega"] = clean["data_entrega"].isoformat()
    return clean
