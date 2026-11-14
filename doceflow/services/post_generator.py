"""Geração de posts para Instagram (Feed 1080×1080 e Story 1080×1920) com Pillow.

Garantias de layout:
- cada elemento (selo, logo, foto, título, preço, chamada) tem uma área própria,
  sem sobreposição, dentro das margens de segurança (no Story, fora das faixas
  superior/inferior onde o Instagram desenha a interface);
- textos quebram em linhas e diminuem até caber; se nem no tamanho mínimo
  couberem, são abreviados com "…" e o resultado informa `truncated`;
- a foto mantém a proporção: "preencher" recorta as bordas, "inteira" encaixa
  com faixas na cor do template; nunca há distorção;
- o logo original é apenas redimensionado proporcionalmente (sem recorte ou recoloração).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO

from PIL import Image, ImageDraw, ImageOps

from services.brand import COLORS, LOGO_PATH, load_font

FORMATS = {"feed": (1080, 1080), "story": (1080, 1920)}
FORMAT_LABELS = {"feed": "Feed 1080×1080", "story": "Story 1080×1920"}
FIT_MODES = {"cover": "Preencher (recorta bordas)", "contain": "Mostrar foto inteira"}

TEMPLATES = {
    "produto": {
        "nome": "Divulgação de produto", "selo": "DESTAQUE",
        "fundo": COLORS["algodao"], "texto": COLORS["chocolate"], "preco": COLORS["chocolate"],
        "selo_fundo": COLORS["cobertura"], "selo_texto": COLORS["chocolate"],
        "cta_fundo": COLORS["chocolate"], "cta_texto": COLORS["algodao"], "moldura": COLORS["cobertura"],
        "placeholder": COLORS["algodao"], "confete": False,
    },
    "promocao": {
        "nome": "Promoção especial", "selo": "PROMOÇÃO ESPECIAL",
        "fundo": COLORS["chocolate"], "texto": COLORS["algodao"], "preco": COLORS["cobertura"],
        "selo_fundo": COLORS["coracao"], "selo_texto": COLORS["branco"],
        "cta_fundo": COLORS["coracao"], "cta_texto": COLORS["branco"], "moldura": COLORS["coracao"],
        "placeholder": COLORS["algodao"], "confete": False,
    },
    "novidade": {
        "nome": "Novidade do catálogo", "selo": "NOVIDADE",
        "fundo": COLORS["algodao"], "texto": COLORS["chocolate"], "preco": COLORS["chocolate"],
        "selo_fundo": COLORS["coracao"], "selo_texto": COLORS["branco"],
        "cta_fundo": COLORS["coracao"], "cta_texto": COLORS["branco"], "moldura": COLORS["coracao"],
        "placeholder": COLORS["algodao"], "confete": True,
    },
}

# Áreas (x0, y0, x1, y1) por formato. Story: Instagram cobre ~250 px no topo e na base.
LAYOUTS = {
    "feed": {
        "margin": 64, "header": (64, 56, 1016, 176), "photo": (64, 196, 1016, 612),
        "title": (64, 632, 1016, 792), "price": (64, 800, 1016, 880), "cta": (64, 912, 1016, 1008),
        "logo_size": 116, "title_max": 3, "price_max": 2, "title_sizes": (68, 36), "price_sizes": (56, 30), "cta_size": (38, 24),
        "badge_size": (34, 22),
    },
    "story": {
        "margin": 80, "header": (80, 250, 1000, 400), "photo": (80, 430, 1000, 1150),
        "title": (80, 1180, 1000, 1420), "price": (80, 1436, 1000, 1536), "cta": (80, 1566, 1000, 1670),
        "logo_size": 146, "title_max": 3, "price_max": 2, "title_sizes": (84, 44), "price_sizes": (64, 34), "cta_size": (42, 26),
        "badge_size": (40, 26),
    },
}
LINE_SPACING = 1.18


@dataclass
class PostContent:
    title: str
    price: str
    cta: str
    photo: Image.Image | None = None
    fit: str = "cover"


@dataclass
class PostResult:
    png: bytes
    size: tuple[int, int]
    boxes: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    font_sizes: dict[str, int] = field(default_factory=dict)
    truncated: list[str] = field(default_factory=list)
    photo_upscale: float = 1.0  # > 2 indica foto pequena para a área (fica borrada)


def photo_scale(photo_size: tuple[int, int], box_size: tuple[int, int], mode: str) -> float:
    """Quanto a foto precisa ser ampliada para ocupar a área no modo escolhido."""
    sx, sy = box_size[0] / photo_size[0], box_size[1] / photo_size[1]
    return max(sx, sy) if mode == "cover" else min(sx, sy)


# ------------------------------------------------------------------ texto
def _text_width(font, text: str) -> int:
    left, _, right, _ = font.getbbox(text)
    return right - left


def _wrap(text: str, font, max_w: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if _text_width(font, candidate) <= max_w:
                current = candidate
                continue
            if current:
                lines.append(current)
            # palavra sozinha maior que a largura: quebra por caracteres
            while _text_width(font, word) > max_w and len(word) > 1:
                cut = len(word)
                while cut > 1 and _text_width(font, word[:cut] + "-") > max_w:
                    cut -= 1
                lines.append(word[:cut] + "-")
                word = word[cut:]
            current = word
        lines.append(current)
    return [line for line in lines if line] or [""]


def _ellipsize(text: str, font, max_w: int) -> str:
    if _text_width(font, text) <= max_w:
        return text
    while text and _text_width(font, text + "…") > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def fit_text(text: str, role: str, box: tuple, sizes: tuple[int, int], max_lines: int):
    """Maior fonte em que o texto cabe na área. Retorna (fonte, linhas, tamanho, truncado)."""
    x0, y0, x1, y1 = box
    max_w, max_h = x1 - x0, y1 - y0
    big, small = sizes
    text = " ".join(text.split()) if "\n" not in text else text.strip()
    for size in range(big, small - 1, -2):
        font = load_font(role, size)
        lines = _wrap(text, font, max_w)
        if len(lines) <= max_lines and len(lines) * size * LINE_SPACING <= max_h:
            return font, lines, size, False
    font = load_font(role, small)
    lines = _wrap(text, font, max_w)
    max_fit = max(1, min(max_lines, int(max_h // (small * LINE_SPACING))))
    if len(lines) > max_fit:
        lines = lines[:max_fit]
        lines[-1] = _ellipsize(lines[-1] + " …", font, max_w)
    return font, lines, small, True


def _draw_lines(draw, lines, font, size, box, color, align="center") -> tuple:
    x0, y0, x1, y1 = box
    line_h = size * LINE_SPACING
    total_h = line_h * len(lines)
    y = y0 + (y1 - y0 - total_h) / 2
    bounds = [x1, y1, x0, y0]
    for line in lines:
        w = _text_width(font, line)
        x = x0 + (x1 - x0 - w) / 2 if align == "center" else x0
        draw.text((x, y + line_h / 2), line, font=font, fill=color, anchor="lm")
        bb = draw.textbbox((x, y + line_h / 2), line, font=font, anchor="lm")
        bounds = [min(bounds[0], bb[0]), min(bounds[1], bb[1]), max(bounds[2], bb[2]), max(bounds[3], bb[3])]
        y += line_h
    return tuple(int(v) for v in bounds)


# ------------------------------------------------------------------ imagens
def fit_photo(photo: Image.Image, box_size: tuple[int, int], mode: str, background: str) -> Image.Image:
    """Ajusta a foto à área sem distorcer (mesma escala em X e Y)."""
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    w, h = box_size
    if mode == "contain":
        scale = min(w / photo.width, h / photo.height)
        resized = photo.resize((max(1, round(photo.width * scale)), max(1, round(photo.height * scale))),
                               Image.LANCZOS)
        canvas = Image.new("RGB", box_size, background)
        canvas.paste(resized, ((w - resized.width) // 2, (h - resized.height) // 2))
        return canvas
    return ImageOps.fit(photo, box_size, Image.LANCZOS, centering=(0.5, 0.5))


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _logo(size: int) -> Image.Image | None:
    if not LOGO_PATH.exists():
        return None
    logo = Image.open(LOGO_PATH).convert("RGBA")
    logo.thumbnail((size, size), Image.LANCZOS)  # só redimensiona, mantendo a proporção
    return logo


def _confetti(draw, size, protected: list[tuple], colors: list[str]) -> None:
    """Pontinhos decorativos só nas margens livres (nunca sobre texto, foto ou logo)."""
    w, h = size
    spots = [(0.03, 0.30), (0.97, 0.36), (0.02, 0.55), (0.975, 0.62), (0.04, 0.80), (0.96, 0.86),
             (0.5, 0.012), (0.25, 0.988), (0.75, 0.988)]
    for i, (fx, fy) in enumerate(spots):
        cx, cy, r = int(fx * w), int(fy * h), 9 + (i % 3) * 3
        dot = (cx - r, cy - r, cx + r, cy + r)
        if any(_intersects(dot, p) for p in protected):
            continue
        draw.ellipse(dot, fill=colors[i % len(colors)])


def _intersects(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


# ------------------------------------------------------------------ post
def render_post(template_key: str, fmt: str, content: PostContent) -> PostResult:
    if template_key not in TEMPLATES:
        raise ValueError(f"Template desconhecido: {template_key}")
    if fmt not in FORMATS:
        raise ValueError(f"Formato desconhecido: {fmt}")
    t, lay, size = TEMPLATES[template_key], LAYOUTS[fmt], FORMATS[fmt]
    canvas = Image.new("RGB", size, t["fundo"])
    draw = ImageDraw.Draw(canvas)
    result = PostResult(png=b"", size=size)

    # Cabeçalho: selo à esquerda, logo à direita (em uma placa clara, sem alterar o logo)
    hx0, hy0, hx1, hy1 = lay["header"]
    logo_size = lay["logo_size"]
    logo = _logo(logo_size)
    if logo is not None:
        plate = (hx1 - logo.width - 12, hy0 + (hy1 - hy0 - logo.height) // 2 - 6,
                 hx1, hy0 + (hy1 - hy0 + logo.height) // 2 + 6)
        if t["fundo"] != COLORS["algodao"]:
            draw.rounded_rectangle(plate, radius=24, fill=COLORS["algodao"])
        canvas.paste(logo, (plate[0] + 6, plate[1] + 6), logo)
        result.boxes["logo"] = plate
        badge_limit = plate[0] - 24
    else:
        badge_limit = hx1
    badge_area = (hx0 + 28, hy0, badge_limit - 28, hy1)
    font, lines, fsize, cut = fit_text(t["selo"], "body_bold", badge_area, lay["badge_size"], 1)
    text_w = _text_width(font, lines[0])
    pill_h = int(fsize * 1.9)
    pill = (hx0, hy0 + (hy1 - hy0 - pill_h) // 2, hx0 + text_w + 56, hy0 + (hy1 - hy0 + pill_h) // 2)
    draw.rounded_rectangle(pill, radius=pill_h // 2, fill=t["selo_fundo"])
    _draw_lines(draw, lines, font, fsize, pill, t["selo_texto"])
    result.boxes["badge"] = pill
    result.font_sizes["badge"] = fsize

    # Foto (ou espaço com o logo, quando o produto não tem foto)
    px0, py0, px1, py1 = lay["photo"]
    pw, ph = px1 - px0, py1 - py0
    if content.photo is not None:
        result.photo_upscale = round(photo_scale(content.photo.size, (pw, ph), content.fit), 2)
        photo = fit_photo(content.photo, (pw, ph), content.fit, t["placeholder"])
    else:
        photo = Image.new("RGB", (pw, ph), t["placeholder"])
        big_logo = _logo(int(min(pw, ph) * 0.6))
        if big_logo is not None:
            photo.paste(big_logo, ((pw - big_logo.width) // 2, (ph - big_logo.height) // 2), big_logo)
    canvas.paste(photo, (px0, py0), _rounded_mask((pw, ph), 36))
    draw.rounded_rectangle((px0, py0, px1 - 1, py1 - 1), radius=36, outline=t["moldura"], width=6)
    result.boxes["photo"] = lay["photo"]

    # Textos
    for key, role, sizes, max_lines, color in (
        ("title", "title", lay["title_sizes"], lay["title_max"], t["texto"]),
        ("price", "body_bold", lay["price_sizes"], lay["price_max"], t["preco"]),
    ):
        text = getattr(content, key).strip()
        if not text:
            continue
        font, lines, fsize, cut = fit_text(text, role, lay[key], sizes, max_lines)
        result.boxes[key] = _draw_lines(draw, lines, font, fsize, lay[key], color)
        result.font_sizes[key] = fsize
        if cut:
            result.truncated.append(key)

    # Chamada para ação em pílula
    if content.cta.strip():
        cx0, cy0, cx1, cy1 = lay["cta"]
        inner = (cx0 + 40, cy0, cx1 - 40, cy1)
        font, lines, fsize, cut = fit_text(content.cta, "body_bold", inner, lay["cta_size"], 1)
        width = _text_width(font, lines[0]) + 96
        mid = (cx0 + cx1) // 2
        pill = (max(cx0, mid - width // 2), cy0, min(cx1, mid + width // 2), cy1)
        draw.rounded_rectangle(pill, radius=(cy1 - cy0) // 2, fill=t["cta_fundo"])
        _draw_lines(draw, lines, font, fsize, pill, t["cta_texto"])
        result.boxes["cta"] = pill
        result.font_sizes["cta"] = fsize
        if cut:
            result.truncated.append("cta")

    if t["confete"]:
        _confetti(draw, size, list(result.boxes.values()), [COLORS["coracao"], COLORS["cobertura"]])

    buffer = BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    result.png = buffer.getvalue()
    return result


def generate_post(kind: str, product) -> bytes:
    """Compatibilidade: post de feed com os dados padrão do produto."""
    from services.caption_generator import default_post_texts, product_photo

    texts = default_post_texts(product, kind)
    return render_post(kind, "feed", PostContent(photo=product_photo(product), **texts)).png
