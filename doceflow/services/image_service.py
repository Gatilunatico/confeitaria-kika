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

from PIL import Image, ImageOps, UnidentifiedImageError

log = logging.getLogger("doceflow.images")

BUCKET = "product-images"
MAX_BYTES = 5 * 1024 * 1024
MAX_IMAGES_PER_PRODUCT = 10  # igual ao gatilho da migração 009
MAX_SIDE = 1600  # px: suficiente para a vitrine e leve no celular
ACCEPTED_EXTENSIONS = ("jpg", "jpeg", "png", "webp")
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


def prepare_image(data: bytes) -> tuple[bytes, str, str]:
    """Valida e REPROCESSA a foto: corrige a rotação do celular, reduz para no máximo
    MAX_SIDE px e grava de novo sem metadados (EXIF/GPS). O arquivo salvo é sempre uma
    imagem limpa gerada pelo Pillow, nunca os bytes originais enviados."""
    ext, mime = validate_image(data)
    try:
        with Image.open(BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            out = BytesIO()
            if ext == "jpg":
                img.convert("RGB").save(out, format="JPEG", quality=85, optimize=True)
            elif ext == "png":
                img.save(out, format="PNG", optimize=True)
            else:
                img.save(out, format="WEBP", quality=85)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ImageError("Não foi possível processar a foto. Tente outro arquivo.") from exc
    result = out.getvalue()
    if len(result) > MAX_BYTES:
        raise ImageError("A foto ficou grande demais mesmo reduzida. Tente outra.")
    return result, ext, mime


def image_path(store_id: str, product_id: str, image_id: str, ext: str) -> str:
    for part in (store_id, product_id, image_id):
        uuid.UUID(part)  # impede caminhos arbitrários (ex.: "../")
    return f"{store_id}/{product_id}/{image_id}.{ext}"


def upload_product_image(client, store_id: str, product_id: str, data: bytes, alt_text: str = "",
                         principal: bool = False, order: int = 0) -> dict:
    """Envia a foto e registra em product_images. Se o registro falhar, apaga o arquivo enviado."""
    data, ext, mime = prepare_image(data)
    image_id = str(uuid.uuid4())
    path = image_path(store_id, product_id, image_id, ext)
    try:
        client.storage.from_(BUCKET).upload(path, data, {"content-type": mime, "upsert": "false"})
    except Exception as exc:
        log.error("Falha no upload de foto: %s", type(exc).__name__)
        raise ImageError("Não foi possível enviar a foto agora.") from exc
    row = {"id": image_id, "confeitaria_id": store_id, "produto_id": product_id, "storage_path": path,
           "alt_text": alt_text[:200], "principal": principal, "ordem": order}
    try:
        res = client.table("product_images").insert(row).execute()  # RLS + CHECK do caminho + limite de fotos
        if not res.data:
            raise ImageError("O banco não confirmou o registro da foto.")
    except Exception as exc:
        try:
            client.storage.from_(BUCKET).remove([path])
        except Exception:
            pass
        if isinstance(exc, ImageError):
            raise
        if "limite_fotos" in str(getattr(exc, "message", "") or exc):
            raise ImageError(f"Cada produto pode ter no máximo {MAX_IMAGES_PER_PRODUCT} fotos.") from exc
        log.error("Falha ao registrar foto: %s", type(exc).__name__)
        raise ImageError("Não foi possível registrar a foto (verifique a permissão da conta).") from exc
    return row


def public_url(client, path: str) -> str:
    return client.storage.from_(BUCKET).get_public_url(path)


def delete_product_image(client, image_row: dict) -> None:
    """Apaga o registro (RLS) e depois o arquivo. Se o registro não sair, o arquivo fica."""
    try:
        res = client.table("product_images").delete().eq("id", image_row["id"]).execute()
    except Exception as exc:
        log.error("Falha ao apagar foto: %s", type(exc).__name__)
        raise ImageError("Não foi possível apagar a foto agora.") from exc
    if not res.data:
        raise ImageError("Foto não encontrada nesta confeitaria.")
    remove_files(client, [image_row["storage_path"]])


def remove_files(client, paths: list[str]) -> None:
    """Remove arquivos do Storage. Falha aqui só deixa um arquivo órfão (sem registro), nunca dado quebrado."""
    if not paths:
        return
    try:
        client.storage.from_(BUCKET).remove(paths)
    except Exception as exc:
        log.warning("Arquivos de foto não removidos do Storage: %s", type(exc).__name__)
