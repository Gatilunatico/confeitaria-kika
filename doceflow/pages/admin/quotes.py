"""Gestão de orçamentos (leads): filtros, lista, status e conversa no WhatsApp."""

import logging
from datetime import date, datetime, timezone

import pandas as pd
import streamlit as st

from components.brand_theme import PAGE_ICON

from components.dashboard_metrics import period_filter, render_metrics
from components.data_table import show_table
from components.navigation import admin_header, flash
from config import load_settings
from services.auth_service import require_admin
from services.dashboard_service import BRT, compute_metrics, filter_leads
from services.quote_service import LEAD_STATUSES, STATUS_NEW, STATUS_SOLD, LeadValidationError, format_br_phone
from services.whatsapp_service import build_wa_link

log = logging.getLogger("doceflow.admin")
settings = load_settings()
st.set_page_config(page_title=f"{settings.app_name} · Orçamentos", page_icon=PAGE_ICON, layout="wide")
repo = require_admin(settings)


def _fmt_datetime(value) -> str:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRT).strftime("%d/%m/%Y %H:%M")


def customer_link(lead: dict, store_name: str) -> str | None:
    first_name = (lead.get("cliente_nome") or "").split(" ")[0]
    desired = date.fromisoformat(str(lead["data_desejada"])[:10]).strftime("%d/%m/%Y")
    message = (
        f"Olá, {first_name}! Aqui é da {store_name}. Recebemos sua solicitação {lead['protocolo']} "
        f"de {lead['produto_nome']} para {desired}. Vamos conversar sobre o orçamento?"
    )
    try:
        return build_wa_link(lead["cliente_whatsapp"], message)
    except ValueError:
        return None


try:
    store = repo.get_store()
    all_leads = repo.list_leads()
except Exception as exc:
    log.error("Falha ao listar leads: %s", type(exc).__name__)
    st.error("Não foi possível carregar os leads agora.")
    st.stop()
store_name = store.name if store else settings.store_name
admin_header("Orçamentos")

f1, f2, f3 = st.columns([2, 1, 1])
statuses = f1.multiselect("Status", LEAD_STATUSES, default=list(LEAD_STATUSES), key="flt_status")
start, end = period_filter(f2, f3)
period_leads = filter_leads(all_leads, None, start, end)
render_metrics(compute_metrics(period_leads))

shown = filter_leads(period_leads, statuses)
shown = sorted(shown, key=lambda r: str(r["created_at"]), reverse=True)
shown = sorted(shown, key=lambda r: r["status"] != STATUS_NEW)  # novos primeiro, depois mais recentes

st.subheader(f"Leads ({len(shown)})")
if not shown:
    st.write("Nenhum lead para os filtros escolhidos.")
    st.stop()

show_table(
    pd.DataFrame(
        [
            {
                "Status": r["status"],
                "Recebido em": _fmt_datetime(r["created_at"]),
                "Cliente": r["cliente_nome"],
                "WhatsApp": format_br_phone(r["cliente_whatsapp"]),
                "Produto": f"{r['produto_nome']} · {r['quantidade']} ({r['unidade']})",
                "Data desejada": date.fromisoformat(str(r["data_desejada"])[:10]).strftime("%d/%m/%Y")
                + f" · {r['modalidade']}",
                "Observações": r.get("observacoes") or "",
                "Origem": r.get("origem") or "",
                "Protocolo": r["protocolo"],
                "Conversa": customer_link(r, store_name),
            }
            for r in shown
        ]
    ),
    link_column="Conversa",
    link_text="Abrir WhatsApp",
)

st.subheader("Atualizar atendimento")
by_id = {r["id"]: r for r in shown}
lead_id = st.selectbox(
    "Lead", list(by_id),
    # Sem o status no rótulo: o campo fechado não redesenha o texto depois de salvar (QA2-03).
    format_func=lambda i: f"{by_id[i]['protocolo']} · {by_id[i]['cliente_nome']} · {by_id[i]['produto_nome']}",
    key="sel_lead",
)
lead = by_id[lead_id]
st.markdown(f"Status atual: **{lead['status']}**")
c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
current = LEAD_STATUSES.index(lead["status"]) if lead["status"] in LEAD_STATUSES else 0
new_status = c1.selectbox("Novo status", LEAD_STATUSES, index=current, key=f"new_status_{lead_id}")
link = customer_link(lead, store_name)
if link:
    c2.link_button("Abrir conversa no WhatsApp", link, width="stretch")
st.caption(
    "O botão abre o WhatsApp com uma mensagem pronta para a cliente. Abrir a conversa não envia "
    "nada sozinho e não muda o status: atualize o status abaixo quando avançar no atendimento."
)
confirmed = True
if new_status == STATUS_SOLD and lead["status"] != STATUS_SOLD:
    confirmed = st.checkbox("Confirmo que a venda foi fechada com a cliente (pedido e valor combinados).",
                            key=f"confirm_sale_{lead_id}")
if st.button("Salvar status", type="primary", key="save_status"):
    if new_status == lead["status"]:
        st.info("O status escolhido já é o atual.")
    elif not confirmed:
        st.error("Marque a confirmação para registrar a venda como concluída.")
    else:
        try:
            repo.update_lead_status(lead_id, new_status)
        except LeadValidationError as exc:
            st.error(str(exc))
        except Exception as exc:
            log.error("Falha ao salvar status: %s", type(exc).__name__)
            st.error("Não foi possível salvar o status agora. Nada foi alterado.")
        else:
            flash("success", f"Status de {lead['protocolo']} atualizado para **{new_status}**.")
            st.rerun()

st.caption("Dados pessoais de clientes: use só para o atendimento. Não exporte nem compartilhe.")
