# Identidade visual: Kika Cakes Confeitaria (nov/2026)

Baseada no logo e na paleta enviados pela confeitaria (`Logo Kika Cakes_20261109.pdf`). Ela vale para a **vitrine** (clientes), o **painel** (confeiteira) e as **artes do Estúdio de Marketing**.

## Paleta

| Cor | Hex | Onde é usada |
|---|---|---|
| Creme | `#F2EADF` | fundo das páginas e das artes |
| Rosa-claro | `#F2D0D0` | cartão de apresentação da vitrine, menu do painel, campos, avisos, selos |
| Rosa antigo | `#D9849B` | bordas, molduras, detalhes |
| Rosé | `#D94E73` | destaques, sombra e efeito de passar o mouse no botão principal |
| Pink | `#F24484` | cor-assinatura: círculo do logo, cupcake, botão principal da vitrine, selos "Destaque" |

**Tons derivados, só para legibilidade.** Nenhuma das 5 cores é escura o bastante para texto. Por isso, dois tons do próprio rosé aparecem **apenas** em texto e botões. As medidas de contraste seguem a WCAG AA:

| Tom | Hex | Uso | Contraste |
|---|---|---|---|
| Vinho | `#6B1B36` | todo o texto | 9,6:1 no creme · 8,0:1 no rosa-claro |
| Rosé escuro | `#B8345A` | botões comuns, links, preços, títulos da vitrine | 5,7:1 com branco · 4,8:1 no creme |

**Regras de contraste:**
- Texto branco sobre o pink (3,5:1) só em **texto grande e em negrito**, como no botão "Ver catálogo e pedir orçamento" (1,2rem, peso 800).
- Legendas pequenas ficam com opacidade 0,85 (6,7:1). O padrão do Streamlit (0,6) daria 3,5:1, abaixo do mínimo.

## Logo e símbolo

| Arquivo | Uso |
|---|---|
| `assets/logo/logo-kika-cakes.png` | logo redondo, fundo transparente. Fica no topo da vitrine, no login e no menu do painel |
| `assets/logo/cupcake-rosa.png` | cupcake de traço em pink. Fica ao lado do título de cada página do painel e no menu fechado |
| `assets/logo/cupcake-creme.png` | cupcake em creme, para fundos rosa (artes) |
| `assets/logo/favicon.png` | ícone da aba do navegador, nos dois apps |

Os arquivos foram gerados do logo enviado (círculo recortado) e do cupcake em alta resolução do PDF, com transparência real. Não use o logo esticado nem sobre fundos pink sem margem.

## Tipografia

- **Logo:** fonte **Kitten** (do PDF). Ela não é livre para uso na web, então o nome da marca aparece **como imagem** no logo.
- **Títulos da vitrine:** **Lobster** (Google Fonts), letra cursiva próxima de "Cakes Confeitaria".
- **Textos, painel e botões:** **Nunito** (Google Fonts), arredondada como as letras do logo e legível no celular.

## Onde está no código

| O quê | Arquivo |
|---|---|
| Tema (cores, fontes, cantos, menu do painel) | `.streamlit/config.toml` |
| Paleta e caminhos dos arquivos (fonte única) | `components/brand_theme.py` |
| CSS da vitrine (cartão de apresentação, botão pink, preço, títulos) | `components/product_card.py` |
| Logo no menu e no login do painel | `admin_app.py` e `pages/admin/login.py` |
| Cores das artes de marketing | `marketing/brand.py` e `marketing/post_generator.py` |
| Ilustrações dos produtos sem foto | `assets/default_images/*.svg` (recoloridas na nova paleta) |

Capturas da vitrine e do painel com a nova identidade: `docs/evidencias/identidade_visual/`.
