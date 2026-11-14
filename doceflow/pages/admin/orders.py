"""Gestão de pedidos: lista, busca, filtros, detalhes, atualização de status e histórico.

Só a administradora autenticada da confeitaria chega aqui (require_admin). No Supabase,
o RLS devolve apenas os pedidos dela e só permite alterar status, valor final, data de
entrega e observações internas; o histórico é gravado pelo banco (migração 010).
"""

import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from components.dashboard_metrics import period_filter
from components.data_table import show_table
from components.navigation import admin_header, flash
from config import load_settings
from services.auth_service import require_admin
from services.dashboard_service import BRT
from services.order_service import ORDER_STATUSES, STATUS_WAITING, filter_orders, history_text
from services.product_service import format_brl
from services.quote_service import LeadValidationError, format_br_phone
from services.whatsapp_service import customer_order_link

log = logging.getLogger("doceflow.admin")
settings = load_settings()
st.set_page_config(page_title=f"{settings.app_name} · Pedidos", page_icon="📦", layout="wide")
repo = require_admin(settings)
admin_header("Pedidos")

DATE_FIELDS = {"Data do pedido": "created", "Data desejada pelo cliente": "desired"}


def _money(value) -> str:
    return format_brl(float(value)) if value is not None else "—"


def _day(value) -> str:
    if not value:
        return "—"
    return date.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")


def _when(value) -> str:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRT).strftime("%d/%m/%Y %H:%M")


try:
    orders = repo.list_orders()
except Exception as exc:
    log.error("Falha ao listar pedidos: %s", type(exc).__name__)
    st.error("Não foi possível carregar os pedidos agora. Tente novamente em instantes.")
    st.stop()

waiting = sum(1 for o in orders if o["status"] == STATUS_WAITING)
if waiting:
    st.info(f"**{waiting}** pedido(s) aguardando a sua confirmação de disponibilidade e valor.", icon="🔔")

# ---------------------------------------------------------------- filtros
f1, f2, f3, f4 = st.columns([2, 2, 1.4, 1.4])
query = f1.text_input("Buscar por nome ou protocolo", key="ord_q", placeholder="Ex.: Maria ou PD-261114")
statuses = f2.multiselect("Status", ORDER_STATUSES, key="ord_status", placeholder="Todos")
date_field = f3.selectbox("Filtrar pela", list(DATE_FIELDS), key="ord_date_field")
start, end = period_filter(f4, key_prefix="ord")
visible = filter_orders(orders, query, statuses, start, end, DATE_FIELDS[date_field])

st.caption(f"{len(visible)} de {len(orders)} pedido(s). Valores estimados = preço inicial × quantidade, "
           "calculados pelo sistema; **não** são valores recebidos.")
if not visible:
    st.warning("Nenhum pedido encontrado com esses filtros." if orders else "Ainda não há pedidos registrados.")
    st.stop()

show_table(pd.DataFrame([
    {
        "Protocolo": o["protocolo"],
        "Pedido em": _when(o["created_at"]),
        "Cliente": o["cliente_nome"],
        "Data desejada": _day(o["data_entrega"]),
        "Modalidade": o["modalidade"],
        "Itens": len(o["itens"]),
        "Valor estimado": _money(o.get("valor_estimado")),
        "Valor final": _money(o.get("valor_final")),
        "Status": o["status"],
    }
    for o in visible
]))

# ---------------------------------------------------------------- detalhes
st.subheader("Detalhes do pedido")
by_id = {o["id"]: o for o in visible}
oid = st.selectbox("Pedido", list(by_id), key="sel_order",
                   format_func=lambda i: f"{by_id[i]['protocolo']} · {by_id[i]['cliente_nome']} · {by_id[i]['status']}")
order = by_id[oid]

c_contact, c_delivery = st.columns(2)
with c_contact, st.container(border=True):
    st.markdown("**Contato**")
    st.markdown(f"{order['cliente_nome']}  \nWhatsApp: {format_br_phone(order['cliente_whatsapp'])}")
    link = customer_order_link(order, settings.store_name)
    if link:
        st.link_button("Abrir conversa no WhatsApp", link)
with c_delivery, st.container(border=True):
    st.markdown("**Entrega**")
    st.markdown(f"Data desejada: **{_day(order['data_entrega'])}** · {order['modalidade']}")
    if order.get("endereco_entrega"):
        st.markdown(f"Endereço: {order['endereco_entrega']}")
    st.markdown(f"Observações do cliente: {order.get('observacoes') or '—'}")

st.markdown("**Produtos** (nome e preço registrados no momento do pedido)")
show_table(pd.DataFrame([
    {
        "Produto": i["produto_nome"],
        "Quantidade": f"{i['quantidade']} ({i['unidade']})",
        "Preço unitário (a partir de)": _money(i.get("preco_unitario")) if i.get("preco_unitario") is not None
        else "Sob consulta",
        "Subtotal estimado": _money(i.get("subtotal")),
    }
    for i in order["itens"]
]))
st.markdown(f"**Valor estimado do pedido:** {_money(order.get('valor_estimado'))}"
            + ("" if order.get("valor_estimado") is not None else " (há item sob consulta)")
            + f" · **Valor final combinado:** {_money(order.get('valor_final'))}")

# ---------------------------------------------------------------- atualização
with st.form(f"upd_{oid}"):
    st.markdown("**Atualizar pedido**")
    u1, u2, u3 = st.columns(3)
    status = u1.selectbox("Status", ORDER_STATUSES, index=ORDER_STATUSES.index(order["status"]),
                          key=f"upd_status_{oid}")
    final = u2.number_input("Valor final combinado (R$)", min_value=0.0, step=10.0, format="%.2f",
                            value=float(order["valor_final"]) if order.get("valor_final") is not None else None,
                            placeholder="Ainda não combinado", key=f"upd_final_{oid}",
                            help="Valor acertado com o cliente. Não registra pagamento.")
    delivery = u3.date_input("Data de entrega", value=date.fromisoformat(str(order["data_entrega"])[:10]),
                             format="DD/MM/YYYY", key=f"upd_date_{oid}",
                             min_value=date.today() - timedelta(days=365))
    internal = st.text_area("Observações internas (o cliente não vê)", value=order.get("observacoes_internas") or "",
                            max_chars=1000, key=f"upd_notes_{oid}")
    save = st.form_submit_button("Salvar alterações", type="primary")
if save:
    changes = {}
    if status != order["status"]:
        changes["status"] = status
    current_final = float(order["valor_final"]) if order.get("valor_final") is not None else None
    if final != current_final:
        changes["valor_final"] = final
    if delivery.isoformat() != str(order["data_entrega"])[:10]:
        changes["data_entrega"] = delivery
    if internal != (order.get("observacoes_internas") or ""):
        changes["observacoes_internas"] = internal
    if not changes:
        st.info("Nada foi alterado.")
    else:
        try:
            repo.update_order(oid, changes)
        except LeadValidationError as exc:
            st.error(str(exc))
        except Exception as exc:
            log.error("Falha ao atualizar pedido: %s", type(exc).__name__)
            st.error("Não foi possível salvar o pedido agora. Nada foi alterado.")
        else:
            flash("success", f"Pedido **{order['protocolo']}** atualizado.")
            st.rerun()

# ---------------------------------------------------------------- histórico
with st.expander("Histórico de alterações", expanded=False):
    try:
        history = repo.order_history(oid)
    except Exception as exc:
        log.error("Falha ao ler histórico: %s", type(exc).__name__)
        history = None
        st.error("Não foi possível carregar o histórico agora.")
    if history == []:
        st.caption("Sem alterações registradas.")
    for row in history or []:
        who = "cliente (site)" if not row.get("alterado_por") else "painel"
        st.markdown(f"- {_when(row['alterado_em'])} · {history_text(row)} · _{who}_")

st.caption("Dados pessoais de clientes: use só para o atendimento deste pedido. Não exporte nem compartilhe.")
