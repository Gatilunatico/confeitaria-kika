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


ORDER_METRICS_HELP = (
    "Pedidos registrados no período (pela data do pedido), pelo status atual. "
    "*Valor registrado* = soma dos valores **estimados** (preço inicial × quantidade) dos pedidos não "
    "cancelados. É o valor **solicitado**, não a receita recebida: o valor final é combinado com o "
    "cliente e o pagamento não é controlado pelo sistema."
)


def render_order_metrics(metrics) -> None:
    from services.product_service import format_brl

    # Duas linhas de três: em seis colunas, rótulos e valores como "R$ 1.050,00" ficavam cortados.
    m1, m2, m3 = st.columns(3)
    m4, m5, m6 = st.columns(3)
    m1.metric("Total de pedidos", metrics.total)
    m2.metric("Aguardando confirmação", metrics.waiting)
    m3.metric("Confirmados", metrics.confirmed)
    m4.metric("Em produção", metrics.in_production)
    m5.metric("Entregues", metrics.delivered)
    m6.metric("Valor registrado (estimado)", format_brl(metrics.registered_value))
    extra = (f" {metrics.without_estimate} pedido(s) com item sob consulta não entram na soma."
             if metrics.without_estimate else "")
    st.caption(ORDER_METRICS_HELP + extra)
    if metrics.waiting:
        st.info(f"Você tem **{metrics.waiting}** pedido(s) aguardando confirmação.", icon="🛒")
