"""Remove da tela os elementos do Streamlit e da hospedagem que não fazem parte da loja.

No Streamlit Community Cloud a barra do topo recebe botões da plataforma (ícone do GitHub,
"Fork", menu com opções de desenvolvedor, botão "Deploy"). Eles não têm função para a cliente
e expõem a infraestrutura. O selo "Hosted with Streamlit" e o botão "Manage app" (este só para
quem administra o app no Cloud) ficam FORA do app, na página da plataforma: não dá para removê-los
daqui (veja docs/evidencias/etapa_06/relatorio_auditoria.md).
"""

import streamlit as st

# Seletores estáveis (data-testid) do Streamlit 1.67. A barra lateral e o botão de abri-la
# NÃO estão aqui: o painel administrativo continua com o menu.
_HIDDEN = (
    '[data-testid="stToolbar"]',          # barra de ações do topo (GitHub, Fork, menu ⋮)
    '[data-testid="stToolbarActions"]',
    '[data-testid="stAppDeployButton"]',  # botão "Deploy" (desenvolvimento local)
    '[data-testid="stMainMenu"]', "#MainMenu",
    '[data-testid="stDecoration"]',       # faixa colorida de desenvolvimento no topo
    '[data-testid="stStatusWidget"]',     # "Running…" / avisos de código alterado
    "footer",
)

CHROME_CSS = "<style>" + ", ".join(_HIDDEN) + " {display: none !important; visibility: hidden !important;}</style>"


def hide_platform_chrome() -> None:
    """Chamar uma vez no ponto de entrada (public_app.py / admin_app.py), antes de navigation.run()."""
    st.markdown(CHROME_CSS, unsafe_allow_html=True)
