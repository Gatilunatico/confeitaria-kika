"""Geração de imagens de post (1080 × 1080) para Instagram com a identidade da marca.

Usa o template (cores e título), a imagem do produto e o logo em
assets/logos. Fontes personalizadas podem ser colocadas em assets/fonts
(.ttf); sem elas, usa a fonte padrão do Pillow.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import BASE_DIR
from services.caption_generator import load_template
from services.catalog import Product

SIZE = 1080
LOGO_PATH = BASE_DIR / "assets" / "logos" / "logo-kika-cakes.png"
FONTS_DIR = BASE_DIR / "assets" / "fonts"


# Fontes do sistema com acentos (ç, ã, é), usadas se assets/fonts estiver vazio.
SYSTEM_FONTS = (
    "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)


def _font(size: int) -> ImageFont.ImageFont:
    candidates = [*sorted(FONTS_DIR.glob("*.ttf")), *(Path(p) for p in SYSTEM_FONTS)]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow antigo
        return ImageFont.load_default()


def _product_image(product: Product) -> Image.Image | None:
    path = product.image_path
    if not path or Path(path).suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return None  # ilustrações SVG não são renderizadas pelo Pillow
    return Image.open(path).convert("RGB")


def generate_post(kind: str, product: Product) -> bytes:
    """Retorna o PNG do post."""
    template = load_template(kind)
    colors = template["cores"]
    canvas = Image.new("RGB", (SIZE, SIZE), colors["fundo"])
    draw = ImageDraw.Draw(canvas)

    photo = _product_image(product)
    if photo is not None:
        photo.thumbnail((SIZE - 160, 620))
        canvas.paste(photo, ((SIZE - photo.width) // 2, 120))
    else:
        draw.rounded_rectangle((80, 120, SIZE - 80, 740), radius=40, fill=colors["destaque"])

    title = template["titulo"].format(produto=product.name, descricao="", preco="")
    draw.text((SIZE // 2, 820), title, font=_font(56), fill=colors["texto"], anchor="mm")
    draw.text((SIZE // 2, 900), "Peça seu orçamento pelo link na bio", font=_font(36), fill=colors["texto"],
              anchor="mm")

    if LOGO_PATH.exists():
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo.thumbnail((140, 140))
        canvas.paste(logo, (SIZE - logo.width - 30, SIZE - logo.height - 30), logo)

    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()
