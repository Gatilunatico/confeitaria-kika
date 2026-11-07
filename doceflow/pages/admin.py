"""Painel administrativo do DoceFlow: leads, status, indicadores e produtos.

Acesso:
- Supabase: login da confeiteira pelo Supabase Auth (e-mail e senha). Os dados
  mostrados são só da confeitaria em que ela é owner_user_id (RLS no banco).
- SQLite (testes locais): senha ADMIN_PASSWORD.
Nenhuma chave administrativa (service_role) é usada.
"""

import hmac
import logging
import time
from datetime import date

import pandas as pd
import streamlit as st

from config import load_settings
from database import AdminAccessError, SupabaseRepository, get_repository, get_supabase_client
from services.catalog import (
    PRICE_ON_REQUEST,
    PRICE_TYPE_LABELS,
    PRICE_TYPES,
    available_images,
    validate_product,
)
from services.dashboard import BRT, PERIODS, compute_metrics, created_date_brt, filter_leads, period_range
from services.leads import (
    LEAD_STATUSES,
    STATUS_NEW,
    STATUS_SOLD,
    LeadPersistenceError,
    LeadValidationError,
    format_br_phone,
)
from services.whatsapp import build_wa_link

log = logging.getLogger("doceflow.admin")
settings = load_settings()

st.set_page_config(page_title=f"{settings.app_name} · Painel", page_icon="🔒", layout="wide")

MAX_ATTEMPTS = 5
LOCK_SECONDS = 300
NO_IMAGE = "(sem imagem)"
CUSTOM_PERIOD = "Personalizado"


# ================================================================ autenticação
def _logout() -> None:
    client = st.session_state.pop("admin_client", None)
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    for key in ("admin_ok", "admin_user_id", "admin_repo"):
        st.session_state.pop(key, None)


def _register_failure() -> None:
    attempts = st.session_state.get("login_attempts", 0) + 1
    st.session_state["login_attempts"] = attempts
    if attempts >= MAX_ATTEMPTS:
        st.session_state["login_locked_until"] = time.time() + LOCK_SECONDS
        st.session_state["login_attempts"] = 0


def _login_screen() -> None:
    st.title("Painel administrativo")
    locked_until = st.session_state.get("login_locked_until", 0)
    if time.time() < locked_until:
        minutes = max(1, round((locked_until - time.time()) / 60))
        st.error(f"Muitas tentativas sem sucesso. Tente novamente em {minutes} min.")
        st.stop()

    if settings.db_backend == "supabase":
        with st.form("login"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
        if submitted:
            client = None
            try:
                client = get_supabase_client(settings)
                res = client.auth.sign_in_with_password({"email": email.strip(), "password": password})
                repo = SupabaseRepository.for_owner(client, res.user.id)
            except AdminAccessError as exc:
                if client is not None:
                    client.auth.sign_out()
                st.error(str(exc))
                st.stop()
            except Exception as exc:
                log.warning("Login admin recusado: %s", type(exc).__name__)
                _register_failure()
                st.error("E-mail ou senha inválidos.")
                st.stop()
            st.session_state.update(admin_ok=True, admin_client=client, admin_user_id=res.user.id,
                                    admin_repo=repo, login_attempts=0)
            st.rerun()
        st.stop()

    if not settings.admin_password:
        st.error("Acesso bloqueado: defina ADMIN_PASSWORD no .env para habilitar o painel.")
        st.stop()
    with st.form("login_local"):
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
    if submitted:
        if hmac.compare_digest(password.encode(), settings.admin_password.encode()):
            st.session_state.update(admin_ok=True, login_attempts=0)
            st.rerun()
        _register_failure()
        st.error("Senha incorreta.")
    st.stop()


if not st.session_state.get("admin_ok"):
    _login_screen()


# ================================================================ dados
def _repo():
    if settings.db_backend == "supabase":
        return st.session_state["admin_repo"]
    return get_repository(settings)


def _flash(kind: str, message: str) -> None:
    st.session_state["admin_flash"] = (kind, message)


def _fmt_datetime(value) -> str:
    from datetime import datetime, timezone

    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRT).strftime("%d/%m/%Y %H:%M")


def _customer_link(lead: dict, store_name: str) -> str | None:
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
    repo = _repo()
    store = repo.get_store()
    if store is None:
        raise AdminAccessError("Confeitaria não encontrada.")
except Exception as exc:
    log.error("Falha ao abrir o painel: %s", type(exc).__name__)
    st.error("Não foi possível carregar o painel agora. Tente novamente em instantes.")
    st.button("Sair", on_click=_logout)
    st.stop()

head_left, head_right = st.columns([5, 1], vertical_alignment="center")
head_left.title(f"Painel · {store.name}")
head_right.button("Sair", on_click=_logout, width="stretch")

flash = st.session_state.pop("admin_flash", None)
if flash:
    getattr(st, flash[0])(flash[1])

tab_leads, tab_products = st.tabs(["Leads", "Produtos"])


# ================================================================ leads
with tab_leads:
    try:
        all_leads = repo.list_leads()
    except Exception as exc:
        log.error("Falha ao listar leads: %s", type(exc).__name__)
        st.error("Não foi possível carregar os leads agora.")
        all_leads = []

    f1, f2, f3 = st.columns([2, 1, 1])
    statuses = f1.multiselect("Status", LEAD_STATUSES, default=list(LEAD_STATUSES), key="flt_status")
    period = f2.selectbox("Período (data de registro)", [*PERIODS, CUSTOM_PERIOD], index=3, key="flt_period")
    today = date.today()
    if period == CUSTOM_PERIOD:
        chosen = f3.date_input("De / até", value=(today.replace(day=1), today), format="DD/MM/YYYY", key="flt_range")
        start, end = (chosen[0], chosen[1]) if isinstance(chosen, tuple) and len(chosen) == 2 else (None, None)
    else:
        start, end = period_range(period, today)

    period_leads = filter_leads(all_leads, None, start, end)
    metrics = compute_metrics(period_leads)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total de leads", metrics.total)
    m2.metric("Leads novos", metrics.new)
    m3.metric("Orçamentos enviados", metrics.quotes_sent)
    m4.metric("Vendas concluídas", metrics.sold)
    m5.metric("Taxa de conversão", metrics.conversion_label)
    st.caption(
        "Indicadores do período selecionado. *Total de leads* = solicitações registradas pela vitrine "
        "(não são mensagens enviadas no WhatsApp). *Orçamentos enviados* e *Vendas concluídas* contam o "
        "status atual de cada lead. Venda só conta depois de você marcá-la manualmente. "
        "*Conversão* = vendas concluídas ÷ total de leads."
    )

    if metrics.new:
        st.info(f"Você tem **{metrics.new}** lead(s) novo(s) aguardando atendimento.", icon="🔔")

    shown = filter_leads(period_leads, statuses)
    shown = sorted(shown, key=lambda r: str(r["created_at"]), reverse=True)
    shown = sorted(shown, key=lambda r: r["status"] != STATUS_NEW)  # novos primeiro, depois mais recentes

    st.subheader(f"Leads ({len(shown)})")
    if not shown:
        st.write("Nenhum lead para os filtros escolhidos.")
    else:
        table = pd.DataFrame(
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
                    "Conversa": _customer_link(r, store.name),
                }
                for r in shown
            ]
        )
        st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            column_config={"Conversa": st.column_config.LinkColumn("Conversa", display_text="Abrir WhatsApp")},
        )

        st.subheader("Atualizar atendimento")
        by_id = {r["id"]: r for r in shown}
        lead_id = st.selectbox(
            "Lead",
            list(by_id),
            format_func=lambda i: f"{by_id[i]['protocolo']} · {by_id[i]['cliente_nome']} · "
            f"{by_id[i]['produto_nome']} · {by_id[i]['status']}",
            key="sel_lead",
        )
        lead = by_id[lead_id]
        c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
        current = LEAD_STATUSES.index(lead["status"]) if lead["status"] in LEAD_STATUSES else 0
        new_status = c1.selectbox("Novo status", LEAD_STATUSES, index=current, key=f"new_status_{lead_id}")
        link = _customer_link(lead, store.name)
        if link:
            c2.link_button("Abrir conversa no WhatsApp", link, width="stretch")
        st.caption(
            "O botão abre o WhatsApp com uma mensagem pronta para a cliente. Abrir a conversa não envia "
            "nada sozinho e não muda o status: atualize o status abaixo quando avançar no atendimento."
        )
        confirmed = True
        if new_status == STATUS_SOLD and lead["status"] != STATUS_SOLD:
            confirmed = st.checkbox(
                "Confirmo que a venda foi fechada com a cliente (pedido e valor combinados).",
                key=f"confirm_sale_{lead_id}",
            )
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
                    _flash("success", f"Status de {lead['protocolo']} atualizado para **{new_status}**.")
                    st.rerun()


# ================================================================ produtos
def _product_form(prefix: str, product=None) -> dict:
    images = [NO_IMAGE, *available_images()]
    c1, c2 = st.columns(2)
    values = {
        "name": c1.text_input("Nome *", value=product.name if product else "", max_chars=120, key=f"{prefix}_name"),
        "category": c2.text_input("Categoria *", value=product.category if product else "", max_chars=60,
                                  key=f"{prefix}_cat"),
    }
    values["description"] = st.text_area("Descrição", value=product.description if product else "", max_chars=500,
                                         key=f"{prefix}_desc")
    c3, c4, c5 = st.columns(3)
    values["price_type"] = c3.selectbox(
        "Tipo de preço *", PRICE_TYPES, format_func=PRICE_TYPE_LABELS.get,
        index=PRICE_TYPES.index(product.price_type) if product else 0, key=f"{prefix}_ptype",
    )
    values["price"] = c4.number_input(
        "Preço (R$)", min_value=0.0, step=1.0, format="%.2f",
        value=float(product.price) if product and product.price is not None else 0.0, key=f"{prefix}_price",
        help="Ignorado quando o tipo é 'Sob consulta'. O preço exibido é sempre inicial ou estimado.",
    )
    values["unit"] = c5.text_input("Unidade *", value=product.unit if product else "", max_chars=40,
                                   placeholder="kg, unidade, caixa com 6", key=f"{prefix}_unit")
    c6, c7, c8, c9 = st.columns(4)
    values["min_qty"] = c6.number_input("Qtd. mínima", min_value=1, step=1,
                                        value=product.min_qty if product else 1, key=f"{prefix}_min")
    values["max_qty"] = c7.number_input("Qtd. máxima", min_value=1, step=1,
                                        value=product.max_qty if product else 50, key=f"{prefix}_max")
    values["order"] = c8.number_input("Ordem na vitrine", min_value=0, step=1,
                                      value=product.order if product else 0, key=f"{prefix}_order")
    current_image = product.image if product and product.image in images else NO_IMAGE
    image = c9.selectbox("Imagem", images, index=images.index(current_image), key=f"{prefix}_img")
    values["image"] = None if image == NO_IMAGE else image
    values["available"] = st.checkbox("Disponível para orçamento", value=product.available if product else True,
                                      key=f"{prefix}_avail")
    return values


with tab_products:
    try:
        products = repo.list_products()
    except Exception as exc:
        log.error("Falha ao listar produtos: %s", type(exc).__name__)
        st.error("Não foi possível carregar os produtos agora.")
        products = []

    st.caption("As alterações aparecem na vitrine na próxima vez que a página for carregada.")
    if products:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Produto": p.name,
                        "Categoria": p.category,
                        "Preço na vitrine": p.price_label,
                        "Disponível": "Sim" if p.available else "Não",
                        "Quantidade": f"{p.min_qty} a {p.max_qty} ({p.unit})",
                        "Ordem": p.order,
                    }
                    for p in products
                ]
            ),
            hide_index=True,
            width="stretch",
        )

        st.subheader("Editar produto")
        by_pid = {p.id: p for p in products}
        pid = st.selectbox("Produto", list(by_pid), format_func=lambda i: by_pid[i].name, key="sel_product")
        with st.form(f"edit_{pid}"):
            values = _product_form(f"edit_{pid}", by_pid[pid])
            save = st.form_submit_button("Salvar produto", type="primary")
        if save:
            data, errors = validate_product(values, editing=True)
            if errors:
                st.error("Confira os campos:\n\n" + "\n".join(f"- {m}" for m in errors.values()))
            else:
                try:
                    repo.update_product(pid, data)
                except LeadValidationError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    log.error("Falha ao salvar produto: %s", type(exc).__name__)
                    st.error("Não foi possível salvar o produto agora. Nada foi alterado.")
                else:
                    _flash("success", f"Produto **{data['name']}** atualizado.")
                    st.rerun()

    with st.expander("Cadastrar novo produto", expanded=not products):
        with st.form("new_product", clear_on_submit=False):
            values = _product_form("new")
            create = st.form_submit_button("Cadastrar produto", type="primary")
        if create:
            data, errors = validate_product(values, existing_slugs={p.slug for p in products})
            if data.get("price_type") == PRICE_ON_REQUEST:
                data["price"] = None
            if errors:
                st.error("Confira os campos:\n\n" + "\n".join(f"- {m}" for m in errors.values()))
            else:
                try:
                    repo.create_product(data)
                except LeadValidationError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    log.error("Falha ao cadastrar produto: %s", type(exc).__name__)
                    st.error("Não foi possível cadastrar o produto agora.")
                else:
                    _flash("success", f"Produto **{data['name']}** cadastrado.")
                    st.rerun()

st.caption("Dados pessoais de clientes: use só para o atendimento. Não exporte nem compartilhe.")
