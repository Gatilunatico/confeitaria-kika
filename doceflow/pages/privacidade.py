"""Aviso de privacidade (LGPD) da vitrine."""

import streamlit as st

from config import load_settings

settings = load_settings()
st.set_page_config(page_title=f"Privacidade · {settings.store_name}", page_icon="🔒")

st.title("Aviso de privacidade")
st.write(f"Este aviso explica como a **{settings.store_name}** trata os dados enviados pela vitrine digital.")

st.subheader("Quais dados coletamos")
st.markdown(
    "- **Nome** e **WhatsApp**, para responder ao seu orçamento.\n"
    "- **Detalhes do pedido**: produto, quantidade, data, retirada ou entrega e observações.\n"
    "- **Origem da visita** (ex.: Instagram), se o link tiver essa informação.\n\n"
    "Não pedimos endereço, CPF, e-mail nem dados de pagamento neste formulário."
)

st.subheader("Para que usamos")
st.write(
    "Somente para analisar e responder a sua solicitação de orçamento e acompanhar o atendimento. "
    "Não vendemos nem compartilhamos seus dados com terceiros para marketing."
)

st.subheader("Base legal e consentimento")
st.write(
    "O envio só acontece depois que você marca a caixa de autorização. Registramos a data desse consentimento."
)

st.subheader("Quem acessa")
st.write(
    "Apenas a equipe da confeitaria, com login. Os dados ficam em banco de dados protegido e não são públicos."
)

st.subheader("Por quanto tempo guardamos")
st.write(
    "Pelo tempo necessário para o atendimento do orçamento e obrigações legais. "
    "Depois disso, os dados são excluídos ou anonimizados."
)

st.subheader("Seus direitos")
st.write(
    "Você pode pedir acesso, correção ou exclusão dos seus dados a qualquer momento, "
    "pelo mesmo WhatsApp da confeitaria, informando o número do protocolo."
)

st.markdown("[Voltar ao catálogo](/)")
