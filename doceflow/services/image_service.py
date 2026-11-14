"""Fotos de produtos no Supabase Storage (bucket "product-images").

O app só faz upload com o cliente LOGADO da administradora; as políticas do Storage
e da tabela product_images (migração 006) garantem que ela só escreve na pasta da
própria confeitaria. A leitura das fotos é pública (informação comercial).
Caminho: <confeitaria_id>/<produto_id>/<foto_id>.<ext>
"""

from __future__ import annotations

import logging
import uuid
from io import BytesIO

from PIL import Image, UnidentifiedImageError

log = logging.getLogger("doceflow.images")

BUCKET = "product-images"
MAX_BYTES = 5 * 1024 * 1024
FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}


class ImageError(ValueError):
    """Foto recusada ou falha ao salvar. A mensagem pode ir para a tela."""


def validate_image(data: bytes) -> tuple[str, str]:
    """Confere tamanho e conteúdo REAL do arquivo (não confia na extensão). Retorna (ext, mime)."""
    if not data:
        raise ImageError("Arquivo vazio.")
    if len(data) > MAX_BYTES:
        raise ImageError("A foto passa de 5 MB.")
    try:
        with Image.open(BytesIO(data)) as img:
            img.verify()
            fmt = img.format
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageError("Arquivo não é uma imagem válida (use JPG, PNG ou WEBP).") from exc
    if fmt not in FORMATS:
        raise ImageError("Formato não aceito. Use JPG, PNG ou WEBP.")
    return FORMATS[fmt]


def image_path(store_id: str, product_id: str, image_id: str, ext: str) -> str:
    for part in (store_id, product_id, image_id):
        uuid.UUID(part)  # impede caminhos arbitrários (ex.: "../")
    return f"{store_id}/{product_id}/{image_id}.{ext}"


def upload_product_image(client, store_id: str, product_id: str, data: bytes, alt_text: str = "",
                         principal: bool = False) -> dict:
    """Envia a foto e registra em product_images. Se o registro falhar, apaga o arquivo enviado."""
    ext, mime = validate_image(data)
    image_id = str(uuid.uuid4())
    path = image_path(store_id, product_id, image_id, ext)
    try:
        client.storage.from_(BUCKET).upload(path, data, {"content-type": mime, "upsert": "false"})
    except Exception as exc:
        log.error("Falha no upload de foto: %s", type(exc).__name__)
        raise ImageError("Não foi possível enviar a foto agora.") from exc
    row = {"id": image_id, "confeitaria_id": store_id, "produto_id": product_id, "storage_path": path,
           "alt_text": alt_text[:200], "principal": principal}
    try:
        res = client.table("product_images").insert(row).execute()
        if not res.data:
            raise ImageError("O banco não confirmou o registro da foto.")
    except Exception as exc:
        try:
            client.storage.from_(BUCKET).remove([path])
        except Exception:
            pass
        if isinstance(exc, ImageError):
            raise
        log.error("Falha ao registrar foto: %s", type(exc).__name__)
        raise ImageError("Não foi possível registrar a foto (verifique a permissão da conta).") from exc
    return row


def public_url(client, path: str) -> str:
    return client.storage.from_(BUCKET).get_public_url(path)


def delete_product_image(client, image_row: dict) -> None:
    try:
        client.table("product_images").delete().eq("id", image_row["id"]).execute()
        client.storage.from_(BUCKET).remove([image_row["storage_path"]])
    except Exception as exc:
        log.error("Falha ao apagar foto: %s", type(exc).__name__)
        raise ImageError("Não foi possível apagar a foto agora.") from exc
