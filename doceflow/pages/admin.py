<<<<<<< Updated upstream
"""Painel administrativo: consulta de leads da confeitaria.

- SQLite (testes locais): senha provisória ADMIN_PASSWORD.
- Supabase: login da dona via Supabase Auth (e-mail e senha). O RLS só
  devolve os leads da confeitaria cujo owner_user_id é o usuário logado.
  Nenhuma chave administrativa (service_role) é usada.
"""

import hmac
import logging

import pandas as pd
=======
"""Authenticated operational administration for one server-configured bakery."""
from uuid import uuid4
>>>>>>> Stashed changes
import streamlit as st
from config import load_settings
<<<<<<< Updated upstream
from database import SupabaseRepository, check_connection, get_repository, get_supabase_client
=======
from services.auth import authenticate, session_token
from services.repository import Repository, STATUSES, indicators
from services.catalog import Product, PRICE_FROM, PRICE_ESTIMATED, PRICE_ON_REQUEST
from services.whatsapp import build_wa_link
>>>>>>> Stashed changes

log = logging.getLogger("doceflow.admin")
settings = load_settings()
<<<<<<< Updated upstream

st.set_page_config(page_title=f"{settings.app_name} · Admin", page_icon="🔒", layout="wide")
st.title("Painel administrativo")


def _logout() -> None:
    client = st.session_state.pop("admin_client", None)
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    st.session_state.pop("admin_ok", None)


# ---------------------------------------------------------------- login
if not st.session_state.get("admin_ok"):
    if settings.db_backend == "supabase":
        with st.form("login"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
        if submitted:
            try:
                client = get_supabase_client(settings)
                client.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state["admin_client"] = client
                st.session_state["admin_ok"] = True
                st.rerun()
            except Exception as exc:
                log.warning("Login admin recusado: %s", type(exc).__name__)
                st.error("E-mail ou senha inválidos.")
        st.stop()

    if not settings.admin_password:
        st.error("Acesso bloqueado: defina ADMIN_PASSWORD no .env para habilitar o painel.")
        st.stop()
    with st.form("login_local"):
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")
    if submitted:
        if hmac.compare_digest(password.encode(), settings.admin_password.encode()):
            st.session_state["admin_ok"] = True
=======
st.set_page_config(page_title=f'{settings.app_name} · Admin', page_icon='🔒', layout='wide')
st.title('Painel administrativo')
if not settings.admin_password:
    st.error('Acesso bloqueado: defina ADMIN_PASSWORD para habilitar o painel.')
    st.stop()
if st.session_state.get('admin_token') != session_token(settings):
    with st.form('login'):
        password = st.text_input('Senha', type='password')
        submitted = st.form_submit_button('Entrar')
    if submitted:
        if authenticate(password, settings):
            st.session_state['admin_token'] = session_token(settings)
>>>>>>> Stashed changes
            st.rerun()
        else:
            st.error('Senha incorreta.')
    st.stop()
if st.button('Sair'):
    st.session_state.clear()
    st.rerun()
st.success('Acesso liberado.')
st.caption(settings.store_name)
try:
    repo = Repository(settings)
except Exception:
    st.error('Não foi possível abrir o banco administrativo. Confira a configuração do servidor.')
    st.stop()

<<<<<<< Updated upstream

# ---------------------------------------------------------------- painel
st.success("Acesso liberado.")
status = check_connection(settings)
(st.info if status.ok else st.error)(f"Banco: {status.backend}. {status.detail}")

try:
    if settings.db_backend == "supabase":
        repo = SupabaseRepository(st.session_state["admin_client"], settings.store_slug)
    else:
        repo = get_repository(settings)
    leads = repo.list_leads()
except Exception as exc:
    log.error("Falha ao listar leads: %s", type(exc).__name__)
    st.error("Não foi possível carregar os leads agora.")
    leads = []

st.subheader(f"Leads ({len(leads)})")
if leads:
    df = pd.DataFrame(leads).rename(
        columns={
            "protocolo": "Protocolo", "created_at": "Recebido em", "status": "Status",
            "cliente_nome": "Cliente", "cliente_whatsapp": "WhatsApp", "produto_nome": "Produto",
            "quantidade": "Qtd.", "unidade": "Unidade", "data_desejada": "Data desejada",
            "modalidade": "Retirada/Entrega", "observacoes": "Observações", "origem": "Origem",
        }
    )
    st.dataframe(df, hide_index=True, width="stretch")
else:
    st.write("Nenhuma solicitação recebida ainda.")

st.caption("Dados pessoais de clientes: não exporte, não compartilhe e não tire prints desnecessários.")
st.button("Sair", on_click=_logout)
=======
leads_tab, products_tab = st.tabs(['Atendimento', 'Produtos'])
with leads_tab:
    st.caption('Período pela data de registro. Indicadores refletem os filtros e o status atual. Abrir WhatsApp não comprova envio de mensagem.')
    c1, c2, c3 = st.columns(3)
    status = c1.selectbox('Status', ['todos', *STATUSES], format_func=lambda s: 'Todos' if s == 'todos' else STATUSES[s])
    start = c2.date_input('Registro desde', value=None, format='DD/MM/YYYY')
    end = c3.date_input('Registro até', value=None, format='DD/MM/YYYY')
    if start and end and start > end:
        st.error('Data inicial deve ser anterior ou igual à final.')
        leads = []
    else:
        leads = repo.all(None if status == 'todos' else status, start, end)
    for col, (label, value) in zip(st.columns(5), indicators(leads).items()):
        col.metric(label, value)
    if not leads:
        st.info('Nenhuma solicitação neste filtro.')
    else:
        st.dataframe([{'Protocolo': q.protocol, 'Nome': q.customer_name, 'Produto': q.product_name,
                       'Registro': q.created_at.strftime('%d/%m/%Y %H:%M'), 'Data desejada': q.desired_date.strftime('%d/%m/%Y'),
                       'Contato': q.whatsapp, 'Status': STATUSES[q.status]} for q in leads], hide_index=True)
        protocol = st.selectbox('Solicitação para atender', [q.protocol for q in leads],
                                format_func=lambda p: next(f'{q.customer_name} · {q.product_name} · {p}' for q in leads if q.protocol == p))
        lead = next(q for q in leads if q.protocol == protocol)
        st.write(f'Quantidade: {lead.quantity} ({lead.unit}) · {lead.fulfillment}')
        st.text(lead.notes or 'Sem observações.')
        st.link_button('Abrir conversa no WhatsApp', build_wa_link(lead.whatsapp, f'Olá! Vamos conversar sobre sua solicitação {lead.protocol}.'))
        with st.form(f'status_{protocol}'):
            new_status = st.selectbox('Novo status', list(STATUSES), index=list(STATUSES).index(lead.status), format_func=STATUSES.get)
            confirmed = st.checkbox('Confirmo que esta venda foi concluída com a cliente')
            if st.form_submit_button('Salvar status'):
                try:
                    repo.update_status(protocol, new_status, confirmed)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
with products_tab:
    products = repo.products()
    selected = st.selectbox('Editar produto ou cadastrar', ['novo', *[p.id for p in products]],
                            format_func=lambda p: 'Cadastrar novo produto' if p == 'novo' else next(x.name for x in products if x.id == p))
    product = next((p for p in products if p.id == selected), None)
    with st.form(f'product_{selected}'):
        name = st.text_input('Nome do produto', value=product.name if product else '', max_chars=100)
        category = st.text_input('Categoria', value=product.category if product else '', max_chars=60)
        description = st.text_area('Descrição', value=product.description if product else '', max_chars=500)
        unit = st.text_input('Unidade', value=product.unit if product else 'unidade', max_chars=40)
        types = [PRICE_FROM, PRICE_ESTIMATED, PRICE_ON_REQUEST]
        price_type = st.selectbox('Tipo de preço', types, index=types.index(product.price_type) if product else 0,
                                  format_func=lambda t: {PRICE_FROM:'A partir de', PRICE_ESTIMATED:'Estimado', PRICE_ON_REQUEST:'Sob consulta'}[t])
        price = st.number_input('Preço (R$)', min_value=0.0, value=float(product.price or 0) if product else 0.0, step=0.5)
        available = st.checkbox('Disponível', value=product.available if product else True)
        minimum = st.number_input('Quantidade mínima', min_value=1, max_value=1000, value=product.min_qty if product else 1)
        maximum = st.number_input('Quantidade máxima', min_value=1, max_value=1000, value=product.max_qty if product else 50)
        if st.form_submit_button('Salvar produto'):
            try:
                repo.save_product(Product(product.id if product else uuid4().hex, name.strip(), category.strip(), description.strip(),
                                          unit.strip(), None if price_type == PRICE_ON_REQUEST else price, price_type, available,
                                          product.image if product else 'cupcakes.svg', minimum, maximum))
                st.success('Produto salvo. A vitrine usará os dados atualizados.')
            except ValueError as exc:
                st.error(str(exc))
>>>>>>> Stashed changes
