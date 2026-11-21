"""Navegação e elementos comuns da área administrativa."""

import streamlit as st

from components.brand_theme import CUPCAKE_PATH
from services.auth_service import LOGIN_PAGE, logout

FLASH_KEY = "admin_flash"


def flash(kind: str, message: str) -> None:
    """Mensagem para a próxima execução da página (ex.: depois de st.rerun)."""
    st.session_state[FLASH_KEY] = (kind, message)


def show_flash() -> None:
    message = st.session_state.pop(FLASH_KEY, None)
    if message:
        getattr(st, message[0])(message[1])


def _logout_and_go_to_login() -> None:
    logout(st.session_state)


def admin_header(title: str) -> None:
    """Título da página + botão Sair. A troca de páginas fica no menu lateral do app."""
    icon, left, right = st.columns([0.55, 5, 1], vertical_alignment="center")
    if CUPCAKE_PATH.exists():
        icon.image(str(CUPCAKE_PATH), width=52)  # símbolo da marca ao lado do título
    left.title(title)
    if right.button("Sair", width="stretch", key="admin_logout"):
        _logout_and_go_to_login()
        st.switch_page(LOGIN_PAGE)
    show_flash()


def page_link(page: str, label: str, icon: str | None = None, fallback_url: str | None = None) -> None:
    """st.page_link mantém a sessão; fora do app principal (testes isolados) cai num link simples."""
    try:
        st.page_link(page, label=label, icon=icon)
    except Exception:
        if fallback_url:
            st.markdown(f"[{label}]({fallback_url})")
