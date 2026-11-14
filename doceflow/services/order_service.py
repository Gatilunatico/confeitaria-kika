"""Pedidos: validação, resumo para o cliente, filtros e indicadores do painel.

Orçamento x pedido:
- Lead (orçamento): contato para tirar dúvidas e receber preço. Fica em `leads`.
- Pedido: o cliente já escolheu produtos e quantidades. Fica em `orders`/`order_items`.
  Nenhum lead vira pedido automaticamente.

Fluxo público: o navegador envia só slug e quantidade de cada produto. O servidor
(função criar_pedido no Supabase, ou o repositório SQLite local) busca nome e preço no
banco, recalcula o valor estimado e grava. O valor estimado é sempre "a partir de":
disponibilidade e preço final dependem da confirmação da confeitaria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from services.dashboard_service import created_date_brt
from services.product_service import PRICE_ON_REQUEST, Product, find_product, format_brl
from services.quote_service import (
    FULFILLMENT_OPTIONS,
    MAX_DAYS_AHEAD,
    NAME_MAX,
    NAME_MIN,
    NOTES_MAX,
    normalize_br_whatsapp,
    normalize_origin,
)

STATUS_WAITING = "Aguardando confirmação"
STATUS_CONFIRMED = "Confirmado"
STATUS_IN_PRODUCTION = "Em produção"
STATUS_READY = "Pronto"
STATUS_DELIVERED = "Entregue"
STATUS_CANCELLED = "Cancelado"
ORDER_STATUSES = (STATUS_WAITING, STATUS_CONFIRMED, STATUS_IN_PRODUCTION, STATUS_READY, STATUS_DELIVERED,
                  STATUS_CANCELLED)
ADMIN_EDITABLE = ("status", "valor_final", "data_entrega", "observacoes_internas")
MAX_ITEMS = 20
ADDRESS_MIN, ADDRESS_MAX = 10, 300
INTERNAL_NOTES_MAX = 1000
DELIVERY = "Entrega"

HISTORY_LABELS = {
    "criado": "Pedido registrado",
    "status": "Status",
    "valor_final": "Valor final",
    "data_entrega": "Data de entrega",
    "observacoes_internas": "Observações internas",
}


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
    address: str = ""

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


@dataclass(frozen=True)
class SummaryLine:
    name: str
    quantity: int
    unit: str
    price_label: str
    subtotal: float | None  # None = sob consulta


@dataclass(frozen=True)
class OrderSummary:
    lines: tuple[SummaryLine, ...]
    total: float | None  # None quando algum item é sob consulta
    has_on_request: bool

    @property
    def total_label(self) -> str:
        if self.total is None:
            return "A combinar (há item com preço sob consulta)"
        return f"A partir de {format_brl(self.total)}"


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
    fulfillment = form.get("fulfillment")
    if fulfillment not in FULFILLMENT_OPTIONS:
        errors["fulfillment"] = "Escolha retirada ou entrega."
    address = " ".join(str(form.get("address") or "").split())
    if fulfillment == DELIVERY:
        if not ADDRESS_MIN <= len(address) <= ADDRESS_MAX:
            errors["address"] = (f"Para entrega, informe o endereço completo (rua, número, bairro e cidade), "
                                 f"com {ADDRESS_MIN} a {ADDRESS_MAX} caracteres.")
    else:
        address = ""  # retirada: não guardamos endereço
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
    return OrderRequest(customer_name=name, whatsapp=phone, delivery_date=delivery, fulfillment=fulfillment,
                        notes=notes, items=tuple(items), consent=True, origin=normalize_origin(form.get("origin")),
                        address=address), {}


def summarize(request: OrderRequest, products: list[Product]) -> OrderSummary:
    """Resumo exibido ANTES da confirmação (o servidor recalcula ao gravar)."""
    lines, total, on_request = [], 0.0, False
    for item in request.items:
        p = find_product(products, item.product_slug)
        if p.price_type == PRICE_ON_REQUEST or p.price is None:
            on_request, subtotal = True, None
        else:
            subtotal = round(p.price * item.quantity, 2)
            total += subtotal
        lines.append(SummaryLine(p.name, item.quantity, p.unit, p.price_label, subtotal))
    return OrderSummary(tuple(lines), None if on_request else round(total, 2), on_request)


def validate_order_update(fields: dict) -> dict:
    """Só os campos que a administradora pode alterar (o banco também restringe por coluna)."""
    unknown = set(fields) - set(ADMIN_EDITABLE)
    if unknown:
        raise ValueError(f"Campos não editáveis: {', '.join(sorted(unknown))}")
    if "status" in fields and fields["status"] not in ORDER_STATUSES:
        raise ValueError("Status de pedido inválido.")
    if fields.get("valor_final") is not None and float(fields["valor_final"]) < 0:
        raise ValueError("O valor final não pode ser negativo.")
    if "observacoes_internas" in fields and len(str(fields["observacoes_internas"])) > INTERNAL_NOTES_MAX:
        raise ValueError(f"Observações internas: no máximo {INTERNAL_NOTES_MAX} caracteres.")
    if "data_entrega" in fields and not isinstance(fields["data_entrega"], (date, str)):
        raise ValueError("Data de entrega inválida.")
    clean = dict(fields)
    if isinstance(clean.get("data_entrega"), date):
        clean["data_entrega"] = clean["data_entrega"].isoformat()
    if clean.get("valor_final") is not None:
        clean["valor_final"] = round(float(clean["valor_final"]), 2)
    return clean


# ================================================================ painel: filtros e indicadores
def _as_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def filter_orders(orders: list[dict], query: str = "", statuses: list[str] | None = None,
                  start: date | None = None, end: date | None = None, by: str = "created") -> list[dict]:
    """Busca por nome ou protocolo; filtro por status e por data (do pedido ou desejada)."""
    q = " ".join(query.lower().split())
    wanted = set(statuses) if statuses else set(ORDER_STATUSES)
    result = []
    for o in orders:
        if o.get("status") not in wanted:
            continue
        if q and q not in str(o.get("cliente_nome", "")).lower() and q not in str(o.get("protocolo", "")).lower():
            continue
        day = created_date_brt(o["created_at"]) if by == "created" else _as_date(o.get("data_entrega"))
        if start and (day is None or day < start):
            continue
        if end and (day is None or day > end):
            continue
        result.append(o)
    return result


@dataclass(frozen=True)
class OrderMetrics:
    total: int
    waiting: int
    confirmed: int
    in_production: int
    delivered: int
    registered_value: float  # soma dos valores ESTIMADOS dos pedidos não cancelados
    without_estimate: int  # pedidos com item sob consulta (sem valor estimado)


def compute_order_metrics(orders: list[dict]) -> OrderMetrics:
    statuses = [o.get("status") for o in orders]
    active = [o for o in orders if o.get("status") != STATUS_CANCELLED]
    return OrderMetrics(
        total=len(orders),
        waiting=statuses.count(STATUS_WAITING),
        confirmed=statuses.count(STATUS_CONFIRMED),
        in_production=statuses.count(STATUS_IN_PRODUCTION),
        delivered=statuses.count(STATUS_DELIVERED),
        registered_value=round(sum(float(o["valor_estimado"]) for o in active
                                   if o.get("valor_estimado") is not None), 2),
        without_estimate=sum(1 for o in active if o.get("valor_estimado") is None),
    )


def history_text(row: dict) -> str:
    """Linha legível do histórico (sem dados pessoais)."""
    label = HISTORY_LABELS.get(row.get("campo"), row.get("campo"))
    if row.get("campo") == "criado":
        return f"{label} pelo site · status {row.get('valor_novo')}"
    old, new = row.get("valor_anterior") or "—", row.get("valor_novo") or "—"
    if row.get("campo") == "valor_final":
        old = format_brl(float(old)) if old != "—" else old
        new = format_brl(float(new)) if new != "—" else new
    if row.get("campo") == "data_entrega":
        old = _as_date(old).strftime("%d/%m/%Y") if old != "—" else old
        new = _as_date(new).strftime("%d/%m/%Y") if new != "—" else new
    if row.get("campo") == "observacoes_internas":
        return f"{label} atualizadas"
    return f"{label}: {old} → {new}"
