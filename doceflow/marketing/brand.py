"""Identidade visual da Kika Cakes Confeitaria (nova identidade, nov/2026).

Paleta oficial (manual da marca): creme #F2EADF, rosa-claro #F2D0D0, rosa antigo #D9849B,
rosé #D94E73 e pink #F24484. Como nenhuma delas é escura, dois tons DERIVADOS do rosé da marca
são usados só onde o texto precisa ser legível (contraste WCAG AA):
- vinho #6B1B36: texto (9,6:1 sobre o creme; 8,0:1 sobre o rosa-claro);
- rosé escuro #B8345A: botões e links com texto branco/claro (5,7:1 com branco).
Logo: círculo pink com "Kika Cakes Confeitaria" (fonte Kitten, só na imagem) e o cupcake de traço.
Nas artes, títulos usam a fonte de título disponível (assets/fonts ou do sistema).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from config import BASE_DIR

from components.brand_theme import (  # noqa: E402  (fonte única da identidade visual)
    CUPCAKE_LIGHT_PATH,
    CUPCAKE_PATH,
    FAVICON_PATH,
    LOGO_PATH,
    PALETTE,
)

COLORS = PALETTE  # nomes usados pelo gerador de artes
FONTS_DIR = BASE_DIR / "assets" / "fonts"
INSTAGRAM_HANDLE = "@kikacakes_confeitaria"

BRAND_FONTS = {
    "title": ["AbrilFatface-Regular.ttf"],
    "body": ["Quicksand-Medium.ttf", "Quicksand[wght].ttf", "Quicksand-Regular.ttf"],
    "body_bold": ["Quicksand-Bold.ttf", "Quicksand[wght].ttf", "Quicksand-SemiBold.ttf"],
}
FALLBACK_FONTS = {
    "title": ["C:/Windows/Fonts/georgiab.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
              "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"],
    "body": ["C:/Windows/Fonts/segoeui.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/System/Library/Fonts/Supplemental/Arial.ttf"],
    "body_bold": ["C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
}


@lru_cache(maxsize=None)
def font_path(role: str) -> str | None:
    """Arquivo de fonte para o papel (title, body, body_bold): marca primeiro, depois sistema."""
    for name in BRAND_FONTS[role]:
        path = FONTS_DIR / name
        if path.exists():
            return str(path)
    for candidate in FALLBACK_FONTS[role]:
        if Path(candidate).exists():
            return candidate
    return None


def using_brand_fonts() -> bool:
    return all(font_path(r) and Path(font_path(r)).parent == FONTS_DIR for r in BRAND_FONTS)


@lru_cache(maxsize=256)
def load_font(role: str, size: int) -> ImageFont.FreeTypeFont:
    path = font_path(role)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)
