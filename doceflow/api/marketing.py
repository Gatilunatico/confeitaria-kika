"""Estúdio de Marketing para o app: prévia da arte, salvar post, listar, mudar status e baixar.

Reaproveita `marketing/post_generator.py` (arte), `marketing/caption_generator.py` (legenda) e
`marketing/store.py` (tabela marketing_posts + bucket privado `marketing`), os mesmos do painel web.
"""

from __future__ import annotations

import base64
import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Response
from PIL import Image
from pydantic import BaseModel, Field

from api.auth import AdminContext, require_admin
from api.errors import ApiError
from marketing.caption_generator import TONES, default_post_texts, generate_caption, suggest_hashtags
from marketing.post_generator import FIT_MODES, FORMAT_LABELS, TEMPLATES, PostContent, render_post
from marketing.store import (
    LIMITS,
    MARKETING_STATUSES,
    DuplicatePostError,
    MarketingError,
    PostDraft,
    SupabaseMarketingStore,
)
from services import image_service

log = logging.getLogger("doceflow.api.marketing")
router = APIRouter(prefix="/v1/marketing", tags=["marketing"])

TemplateKey = Literal["produto", "promocao", "novidade"]
FormatKey = Literal["feed", "story"]
ToneKey = Literal["amigavel", "promocional", "elegante"]
StatusKey = Literal["Rascunho", "Pronto", "Publicado manualmente"]

IDEMPOTENCY_RE = r"^[A-Za-z0-9_-]{8,128}$"
POST_NAMESPACE = uuid.UUID("6f1d3a52-6b1b-4c36-9b2e-7d5e0f1a2c3b")  # ids estáveis por (usuária, chave)
MAX_PHOTO_PIXELS = 40_000_000

# Gerar arte usa CPU: limite por usuária para um toque repetido não travar o servidor.
RENDER_LIMIT, RENDER_WINDOW = 20, 60.0
_render_calls: dict[str, deque] = defaultdict(deque)
_render_lock = threading.Lock()


def check_render_limit(user_id: str) -> None:
    now = time.monotonic()
    with _render_lock:
        calls = _render_calls[user_id]
        while calls and now - calls[0] > RENDER_WINDOW:
            calls.popleft()
        if len(calls) >= RENDER_LIMIT:
            raise ApiError(429, "limite_excedido", "Muitas artes em pouco tempo. Aguarde um minuto.",
                           {"Retry-After": str(int(RENDER_WINDOW))})
        calls.append(now)


# ---------------------------------------------------------------- modelos
class ArteIn(BaseModel):
    produto_id: uuid.UUID
    template: TemplateKey = "produto"
    formato: FormatKey = "feed"
    tom: ToneKey = "amigavel"
    titulo: str | None = Field(default=None, max_length=LIMITS["titulo"])
    preco_texto: str | None = Field(default=None, max_length=LIMITS["preco_texto"])
    cta: str | None = Field(default=None, max_length=LIMITS["cta"])
    extra: str = Field(default="", max_length=300, description="Frase extra na legenda (opcional)")
    usar_foto: bool = True
    imagem_id: uuid.UUID | None = Field(default=None, description="Foto do produto escolhida; vazio = a principal")
    ajuste_foto: Literal["cover", "contain"] = "cover"


class PostIn(ArteIn):
    legenda: str | None = Field(default=None, max_length=LIMITS["legenda"],
                                description="Legenda editada no app; vazio = legenda sugerida")
    status: StatusKey = "Rascunho"


class StatusIn(BaseModel):
    status: StatusKey


# ---------------------------------------------------------------- apoio
def _store(ctx: AdminContext) -> SupabaseMarketingStore:
    return SupabaseMarketingStore(ctx.client, ctx.store.id)


def _product(ctx: AdminContext, product_id: uuid.UUID):
    try:
        products = ctx.repo.list_products()
    except Exception as exc:
        log.error("Falha ao ler produtos: %s", type(exc).__name__)
        raise ApiError(503, "servico_indisponivel", "Catálogo indisponível no momento.") from exc
    for p in products:
        if p.id == str(product_id):
            return p
    raise ApiError(404, "produto_nao_encontrado", "Produto não encontrado nesta confeitaria.")


def _main_photo(ctx: AdminContext, product, image_id: uuid.UUID | None = None) -> Image.Image | None:
    """Foto real do produto (bucket product-images): a escolhida ou a principal, conferida pelo Pillow."""
    try:
        rows = ctx.repo.list_product_images(product.id)
    except Exception:
        return None
    if not rows:
        return None
    if image_id is not None:
        row = next((r for r in rows if str(r.get("id")) == str(image_id)), None)
        if row is None:  # foto de outro produto ou de outra confeitaria
            raise ApiError(404, "foto_nao_encontrada", "Foto não encontrada neste produto.")
    else:
        row = next((r for r in rows if r.get("principal")), rows[0])
    try:
        data = ctx.client.storage.from_(image_service.BUCKET).download(row["storage_path"])
        Image.open(BytesIO(data)).verify()  # arquivo corrompido ou que não é imagem
        photo = Image.open(BytesIO(data))
        if photo.width * photo.height > MAX_PHOTO_PIXELS:
            return None
        photo.load()
        return photo
    except Exception as exc:
        log.warning("Foto do produto indisponível para a arte: %s", type(exc).__name__)
        return None


def _render(ctx: AdminContext, data: ArteIn):
    check_render_limit(ctx.user_id)
    product = _product(ctx, data.produto_id)
    texts = default_post_texts(product, data.template)
    title = data.titulo if data.titulo is not None else texts["title"]
    price = data.preco_texto if data.preco_texto is not None else texts["price"]
    cta = data.cta if data.cta is not None else texts["cta"]
    avisos = []
    photo = _main_photo(ctx, product, data.imagem_id) if data.usar_foto else None
    if data.usar_foto and photo is None:
        avisos.append("sem_foto")  # usa o logo no lugar da foto
    result = render_post(data.template, data.formato,
                         PostContent(title=title, price=price, cta=cta, photo=photo, fit=data.ajuste_foto))
    avisos += [f"texto_abreviado:{campo}" for campo in result.truncated]
    if result.photo_upscale > 2:
        avisos.append("foto_pequena")
    caption = generate_caption(data.template, product, data.tom, data.extra, link=ctx.settings.public_app_url)
    hashtags = suggest_hashtags(product, data.template)
    tail = "\n\n" + " ".join(hashtags)
    body = caption[: -len(tail)] if caption.endswith(tail) else caption
    texts = {"titulo": title, "preco_texto": price, "cta": cta, "legenda_texto": body, "hashtags": hashtags}
    return product, result, texts, caption, avisos


def _marketing_error(exc: MarketingError) -> ApiError:
    text = str(exc)
    if "não encontrad" in text:
        return ApiError(404, "post_nao_encontrado", "Post não encontrado nesta confeitaria.")
    if "permissão" in text:
        return ApiError(403, "sem_permissao", text)
    if "passa de" in text or "inválid" in text:
        return ApiError(422, "dados_invalidos", text)
    return ApiError(503, "servico_indisponivel", text)


# ---------------------------------------------------------------- rotas
@router.get("/opcoes")
def opcoes(_: AdminContext = Depends(require_admin)):
    """Valores aceitos nos campos template, formato, tom, ajuste_foto e status."""
    return {
        "templates": {k: v["nome"] for k, v in TEMPLATES.items()},
        "formatos": FORMAT_LABELS,
        "tons": TONES,
        "ajustes_foto": FIT_MODES,
        "status": list(MARKETING_STATUSES),
        "limites": LIMITS,
    }


@router.post("/previa")
def previa(data: ArteIn, ctx: AdminContext = Depends(require_admin)):
    """Gera a arte e a legenda SEM salvar (para a dona revisar no app)."""
    _, result, textos, caption, avisos = _render(ctx, data)
    return {
        "imagem_png_base64": base64.b64encode(result.png).decode(),
        "largura": result.size[0], "altura": result.size[1],
        "textos": {k: textos[k] for k in ("titulo", "preco_texto", "cta")},
        "legenda": caption, "legenda_texto": textos["legenda_texto"], "hashtags": textos["hashtags"],
        "avisos": avisos,
    }


@router.post("/posts", status_code=201)
def salvar_post(data: PostIn, response: Response, ctx: AdminContext = Depends(require_admin),
                idempotency_key: str = Header(..., alias="Idempotency-Key", pattern=IDEMPOTENCY_RE)):
    """Gera e salva o post. A mesma Idempotency-Key devolve o post já salvo (200), sem duplicar."""
    post_id = str(uuid.uuid5(POST_NAMESPACE, f"{ctx.user_id}:{idempotency_key}"))
    store = _store(ctx)
    try:
        existing = store.get(post_id)
    except MarketingError as exc:
        raise _marketing_error(exc) from exc
    if existing is not None:
        response.status_code = 200
        return {"id": post_id, "criado": False, "post": existing}
    product, result, textos, caption, avisos = _render(ctx, data)
    draft = PostDraft(produto_id=product.id, produto_nome=product.name, template=data.template,
                      formato=data.formato, titulo=textos["titulo"], preco_texto=textos["preco_texto"],
                      cta=textos["cta"], tom=data.tom, legenda=data.legenda or caption, status=data.status)
    try:
        store.save(draft, result.png, post_id=post_id)
    except DuplicatePostError:
        response.status_code = 200
        return {"id": post_id, "criado": False, "post": store.get(post_id)}
    except MarketingError as exc:
        raise _marketing_error(exc) from exc
    log.info("Post de marketing salvo pela API")
    return {"id": post_id, "criado": True, "post": store.get(post_id), "avisos": avisos}


def _scheduled(ctx: AdminContext, post_id: str) -> bool:
    """Post com publicação agendada ou em andamento no Instagram não pode mudar (a fila usa a imagem)."""
    try:
        res = (ctx.client.table("instagram_publications").select("id").eq("marketing_post_id", post_id)
               .in_("status", ["agendado", "publicando"]).limit(1).execute())
        return bool(res.data)
    except Exception:  # sem a migração 014: não existe agendamento
        return False


@router.put("/posts/{post_id}")
def editar_post(post_id: uuid.UUID, data: PostIn, ctx: AdminContext = Depends(require_admin)):
    """Gera a arte de novo com os textos editados e atualiza o rascunho (mesmo id e mesma imagem)."""
    store = _store(ctx)
    try:
        current = store.get(str(post_id))
    except MarketingError as exc:
        raise _marketing_error(exc) from exc
    if current is None:
        raise ApiError(404, "post_nao_encontrado", "Post não encontrado nesta confeitaria.")
    if _scheduled(ctx, str(post_id)):
        raise ApiError(409, "post_agendado", "Este post está agendado no Instagram. Cancele o agendamento para editar.")
    product, result, textos, caption, avisos = _render(ctx, data)
    draft = PostDraft(produto_id=product.id, produto_nome=product.name, template=data.template,
                      formato=data.formato, titulo=textos["titulo"], preco_texto=textos["preco_texto"],
                      cta=textos["cta"], tom=data.tom, legenda=data.legenda or caption, status=data.status)
    try:
        store.update(str(post_id), draft, result.png)
    except MarketingError as exc:
        raise _marketing_error(exc) from exc
    return {"id": str(post_id), "post": store.get(str(post_id)), "avisos": avisos}


@router.get("/posts")
def listar_posts(ctx: AdminContext = Depends(require_admin),
                 pagina: int = Query(1, ge=1, le=10_000), limite: int = Query(20, ge=1, le=100),
                 status: StatusKey | None = None):
    """Posts da confeitaria, do mais novo para o mais antigo, em páginas."""
    try:
        posts = _store(ctx).list()
    except MarketingError as exc:
        raise _marketing_error(exc) from exc
    if status:
        posts = [p for p in posts if p.get("status") == status]
    start = (pagina - 1) * limite
    return {"itens": posts[start:start + limite], "pagina": pagina, "limite": limite, "total": len(posts)}


@router.patch("/posts/{post_id}")
def mudar_status(post_id: uuid.UUID, data: StatusIn, ctx: AdminContext = Depends(require_admin)):
    try:
        _store(ctx).set_status(str(post_id), data.status)
    except MarketingError as exc:
        raise _marketing_error(exc) from exc
    return {"id": str(post_id), "status": data.status}


@router.get("/posts/{post_id}/imagem", response_class=Response,
            responses={200: {"content": {"image/png": {}}}})
def baixar_imagem(post_id: uuid.UUID, ctx: AdminContext = Depends(require_admin)):
    """PNG do post (bucket privado: só a dona da confeitaria consegue baixar)."""
    store = _store(ctx)
    try:
        post = store.get(str(post_id))
        if post is None or not post.get("imagem_path"):
            raise ApiError(404, "post_nao_encontrado", "Post não encontrado nesta confeitaria.")
        png = store.image(post["imagem_path"])
    except MarketingError as exc:
        raise _marketing_error(exc) from exc
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, no-store"})
