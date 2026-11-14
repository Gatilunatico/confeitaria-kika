"""Identidade visual da Kika Cakes (rebranding: confeitaria vintage afetiva).

Cores e tipografia autorizadas no brand book. As fontes da marca são
Abril Fatface (títulos) e Quicksand (textos), licença SIL OFL. Coloque os
arquivos .ttf em assets/fonts com os nomes de BRAND_FONTS; enquanto não
estiverem lá, usamos fontes do sistema com acentos (FALLBACK_FONTS).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

from config import BASE_DIR

COLORS = {
    "algodao": "#FDE8EC",    # fundo
    "cobertura": "#F4A7BB",  # apoio
    "coracao": "#E0628A",    # destaque
    "chocolate": "#5C3317",  # texto
    "branco": "#FFFFFF",
}

LOGO_PATH = BASE_DIR / "assets" / "logos" / "logo-kika-cakes.png"
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
