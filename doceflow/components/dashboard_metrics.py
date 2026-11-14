"""Filtro de período e indicadores comerciais do painel."""

from datetime import date

import streamlit as st

from services.dashboard_service import PERIODS, Metrics, period_range

CUSTOM_PERIOD = "Personalizado"
METRICS_HELP = (
    "Indicadores do período selecionado. *Total de leads* = solicitações registradas pela vitrine "
    "(não são mensagens enviadas no WhatsApp). *Orçamentos enviados* e *Vendas concluídas* contam o "
    "status atual de cada lead. Venda só conta depois de você marcá-la manualmente. "
    "*Conversão* = vendas concluídas ÷ total de leads."
)


def period_filter(column, date_column=None, key_prefix: str = "flt") -> tuple[date | None, date | None]:
    """Seletor de período pela data de registro do lead (7/30/90 dias, tudo ou intervalo)."""
    period = column.selectbox("Período (data de registro)", [*PERIODS, CUSTOM_PERIOD], index=3,
                              key=f"{key_prefix}_period")
    today = date.today()
    if period == CUSTOM_PERIOD:
        target = date_column or column
        chosen = target.date_input("De / até", value=(today.replace(day=1), today), format="DD/MM/YYYY",
                                   key=f"{key_prefix}_range")
        if isinstance(chosen, tuple) and len(chosen) == 2:
            return chosen[0], chosen[1]
        return None, None
    return period_range(period, today)


def render_metrics(metrics: Metrics) -> None:
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total de leads", metrics.total)
    m2.metric("Leads novos", metrics.new)
    m3.metric("Orçamentos enviados", metrics.quotes_sent)
    m4.metric("Vendas concluídas", metrics.sold)
    m5.metric("Taxa de conversão", metrics.conversion_label)
    st.caption(METRICS_HELP)
    if metrics.new:
        st.info(f"Você tem **{metrics.new}** lead(s) novo(s) aguardando atendimento.", icon="🔔")
