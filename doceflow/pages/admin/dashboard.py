"""Painel comercial: indicadores do período e leads novos aguardando atendimento."""

import logging

import streamlit as st

from components.brand_theme import PAGE_ICON

from components.dashboard_metrics import period_filter, render_metrics, render_order_metrics
from components.navigation import admin_header, page_link
from config import load_settings
from services.auth_service import require_admin
from services.dashboard_service import compute_metrics, filter_leads
from services.order_service import compute_order_metrics, filter_orders
from services.quote_service import STATUS_NEW

log = logging.getLogger("doceflow.admin")
settings = load_settings()
st.set_page_config(page_title=f"{settings.app_name} · Painel", page_icon=PAGE_ICON, layout="wide")
repo = require_admin(settings)

try:
    store = repo.get_store()
    all_leads = repo.list_leads()
except Exception as exc:
    log.error("Falha ao abrir o painel: %s", type(exc).__name__)
    st.error("Não foi possível carregar o painel agora. Tente novamente em instantes.")
    st.stop()

admin_header(f"Painel · {store.name if store else settings.store_name}")

f1, f2, _ = st.columns([1, 1, 2])
start, end = period_filter(f1, f2)
period_leads = filter_leads(all_leads, None, start, end)
st.subheader("Orçamentos (leads)")
render_metrics(compute_metrics(period_leads))

new_leads = sorted((r for r in period_leads if r["status"] == STATUS_NEW),
                   key=lambda r: str(r["created_at"]), reverse=True)
if new_leads:
    st.subheader("Aguardando atendimento")
    for r in new_leads[:5]:
        st.markdown(f"- **{r['protocolo']}** · {r['cliente_nome']} · {r['produto_nome']} "
                    f"({r['quantidade']} {r['unidade']})")
st.subheader("Pedidos")
try:
    period_orders = filter_orders(repo.list_orders(), start=start, end=end)
except Exception as exc:  # pedidos fora do ar não derrubam o painel de orçamentos
    log.error("Falha ao carregar pedidos no painel: %s", type(exc).__name__)
    st.warning("Não foi possível carregar os indicadores de pedidos agora.")
else:
    render_order_metrics(compute_order_metrics(period_orders))

st.divider()
c0, c1, c2, c3 = st.columns(4)
with c0:
    page_link("pages/admin/orders.py", "Gerenciar pedidos", "📦")
with c1:
    page_link("pages/admin/quotes.py", "Gerenciar orçamentos", "📋")
with c2:
    page_link("pages/admin/products.py", "Gerenciar produtos", "🧁")
with c3:
    page_link("pages/admin/marketing.py", "Estúdio de Marketing", "📣")
st.caption("Dados pessoais de clientes: use só para o atendimento. Não exporte nem compartilhe.")
