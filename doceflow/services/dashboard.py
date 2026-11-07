"""Regras do painel: filtros de leads e indicadores comerciais.

Definições (exibidas também na tela):
- Total de leads: solicitações REGISTRADAS no período (não mensagens enviadas no WhatsApp).
- Leads novos: status atual "Novo" (ainda sem atendimento).
- Orçamentos enviados: status atual "Orçamento enviado".
- Vendas concluídas: status atual "Venda concluída", marcado manualmente pela confeiteira.
- Taxa de conversão: vendas concluídas / total de leads do período.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from services.leads import (
    LEAD_STATUSES,
    STATUS_NEW,
    STATUS_QUOTE_SENT,
    STATUS_SOLD,
)

BRT = timezone(timedelta(hours=-3))  # horário de Brasília (sem horário de verão)

PERIODS = {
    "Últimos 7 dias": 7,
    "Últimos 30 dias": 30,
    "Últimos 90 dias": 90,
    "Todo o período": None,
}


@dataclass(frozen=True)
class Metrics:
    total: int
    new: int
    quotes_sent: int
    sold: int

    @property
    def conversion_rate(self) -> float | None:
        """Fração de 0 a 1, ou None quando não há leads (evita divisão por zero)."""
        return self.sold / self.total if self.total else None

    @property
    def conversion_label(self) -> str:
        rate = self.conversion_rate
        return "—" if rate is None else f"{rate * 100:.1f}%".replace(".", ",")


def created_date_brt(value) -> date:
    """Data local (Brasília) em que o lead foi registrado."""
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRT).date()


def period_range(label: str, today: date) -> tuple[date | None, date | None]:
    days = PERIODS.get(label)
    if days is None:
        return None, None
    return today - timedelta(days=days - 1), today


def filter_leads(
    leads: list[dict], statuses: list[str] | None = None, start: date | None = None, end: date | None = None
) -> list[dict]:
    """Filtra por status e por data de registro (inclusive)."""
    wanted = set(statuses) if statuses else set(LEAD_STATUSES)
    result = []
    for lead in leads:
        if lead.get("status") not in wanted:
            continue
        day = created_date_brt(lead["created_at"])
        if start and day < start:
            continue
        if end and day > end:
            continue
        result.append(lead)
    return result


def compute_metrics(leads: list[dict]) -> Metrics:
    statuses = [lead.get("status") for lead in leads]
    return Metrics(
        total=len(leads),
        new=statuses.count(STATUS_NEW),
        quotes_sent=statuses.count(STATUS_QUOTE_SENT),
        sold=statuses.count(STATUS_SOLD),
    )
