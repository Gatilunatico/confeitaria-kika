"""Tabela de dados do painel com alternativa em HTML.

`st.dataframe` depende do pyarrow. Em máquinas onde a DLL do pyarrow é
bloqueada (ex.: política de Controle de Aplicativo do Windows), mostramos uma
tabela HTML simples com o mesmo conteúdo e links clicáveis.
"""

from html import escape

import pandas as pd
import streamlit as st


@st.cache_resource(show_spinner=False)
def pyarrow_available() -> bool:
    """Testado uma vez por processo: a tentativa de importar uma DLL bloqueada é lenta."""
    try:
        import pyarrow  # noqa: F401
        return True
    except Exception:
        return False


def show_table(df: pd.DataFrame, link_column: str | None = None, link_text: str = "Abrir") -> None:
    if pyarrow_available():
        config = {link_column: st.column_config.LinkColumn(link_column, display_text=link_text)} if link_column else None
        st.dataframe(df, hide_index=True, width="stretch", column_config=config)
        return
    head = "".join(f"<th>{escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, row in df.iterrows():
        cells = []
        for col, value in row.items():
            if col == link_column and value:
                cells.append(f'<td><a href="{escape(str(value), quote=True)}" target="_blank" rel="noopener">'
                             f"{escape(link_text)}</a></td>")
            else:
                cells.append(f"<td>{escape('' if value is None else str(value))}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    st.markdown(
        f'<div style="overflow-x:auto"><table class="df-table"><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>",
        unsafe_allow_html=True,
    )
