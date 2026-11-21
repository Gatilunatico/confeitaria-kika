"""Identidade visual da Kika Cakes Confeitaria: paleta, arquivos do logo e CSS da marca.

Fonte única das cores: usada pela vitrine, pelo painel e pelo Estúdio de Marketing
(marketing/brand.py reexporta PALETTE como COLORS). Sem dependências pesadas: o app público
importa este módulo sem carregar nada do painel.

Paleta oficial (manual da marca): creme, rosa-claro, rosa antigo, rosé e pink. Nenhuma é escura,
então dois tons DERIVADOS do rosé aparecem só onde o texto precisa ser legível (WCAG AA):
vinho (texto) e rosé escuro (botões e links com texto branco).
"""

from config import BASE_DIR

PALETTE = {
    "creme": "#F2EADF",        # fundo
    "rosa_claro": "#F2D0D0",   # apoio: cartões, selos, campos, menu do painel
    "rosa_antigo": "#D9849B",  # bordas e detalhes
    "rose": "#D94E73",         # destaque
    "pink": "#F24484",         # cor-assinatura (círculo do logo)
    "vinho": "#6B1B36",        # texto: 9,6:1 no creme, 8,0:1 no rosa-claro (derivado)
    "rose_escuro": "#B8345A",  # botões e links: 5,7:1 com texto branco (derivado)
    "branco": "#FFFFFF",
}

LOGO_DIR = BASE_DIR / "assets" / "logo"
LOGO_PATH = LOGO_DIR / "logo-kika-cakes.png"            # círculo pink, fundo transparente
CUPCAKE_PATH = LOGO_DIR / "cupcake-rosa.png"           # símbolo em traço pink
CUPCAKE_LIGHT_PATH = LOGO_DIR / "cupcake-creme.png"    # símbolo para fundos rosa
FAVICON_PATH = LOGO_DIR / "favicon.png"
PAGE_ICON = str(FAVICON_PATH) if FAVICON_PATH.exists() else "🧁"

# Fonte de títulos da vitrine (script, próxima de "Cakes Confeitaria" do logo). O logo em si usa a
# fonte Kitten, que não está disponível livremente na web: por isso o nome da marca aparece como imagem.
SCRIPT_FONT_URL = "https://fonts.googleapis.com/css2?family=Lobster&display=swap"
