"""Gerenciador de fotos de um produto (área administrativa).

Seleção no dispositivo → pré-visualização com validação → envio. Depois, a galeria
permite escolher a foto principal e remover fotos (com confirmação).
A tela valida para dar retorno rápido; quem garante as regras é o servidor:
`image_service.prepare_image` (conteúdo real, tamanho, reprocessamento) e, no
Supabase, as políticas do Storage/RLS e o limite de fotos do banco (migração 009).
"""

from __future__ import annotations

import logging

import streamlit as st

from components.navigation import flash
from services.image_service import ACCEPTED_EXTENSIONS, MAX_BYTES, MAX_IMAGES_PER_PRODUCT, ImageError, validate_image
from services.quote_service import LeadValidationError

log = logging.getLogger("doceflow.admin.fotos")


def _uploader_nonce(pid: str) -> int:
    """Trocar a chave do uploader limpa os arquivos selecionados após um envio."""
    return st.session_state.setdefault(f"upl_nonce_{pid}", 0)


def _check_selected(files) -> list[tuple[object, str | None]]:
    checked = []
    for f in files:
        try:
            validate_image(f.getvalue())
            checked.append((f, None))
        except ImageError as exc:
            checked.append((f, str(exc)))
    return checked


def render_upload(repo, product, images: list[dict]) -> None:
    pid = product.id
    free = MAX_IMAGES_PER_PRODUCT - len(images)
    st.markdown("**Adicionar fotos**")
    if free <= 0:
        st.info(f"Este produto já tem {MAX_IMAGES_PER_PRODUCT} fotos (limite). Remova uma para enviar outra.")
        return
    files = st.file_uploader(
        f"Escolha até {free} foto(s) do computador ou celular",
        type=list(ACCEPTED_EXTENSIONS), accept_multiple_files=True,
        key=f"upl_{pid}_{_uploader_nonce(pid)}",
        help=f"JPG, PNG ou WEBP, até {MAX_BYTES // (1024 * 1024)} MB cada. "
             "As fotos são reduzidas e os dados de localização do celular são removidos.",
    ) or []
    if not files:
        return

    checked = _check_selected(files[:free])
    if len(files) > free:
        st.warning(f"Só cabem mais {free} foto(s): as demais foram ignoradas.")
    st.caption("Pré-visualização")
    cols = st.columns(min(len(checked), 4))
    for i, (f, error) in enumerate(checked):
        with cols[i % len(cols)]:
            if error:
                st.error(f"{f.name}: {error}")
            else:
                st.image(f.getvalue(), caption=f.name, width="stretch")

    valid = [f for f, error in checked if error is None]
    alt = st.text_input("Descrição das fotos (opcional)", max_chars=200, key=f"alt_{pid}",
                        placeholder=f"Ex.: {product.name} decorado para aniversário",
                        help="Ajuda quem usa leitor de tela e aparece se a foto não carregar.")
    if st.button(f"Enviar {len(valid)} foto(s)", type="primary", disabled=not valid, key=f"send_{pid}"):
        sent, failed = 0, []
        with st.spinner("Enviando fotos..."):
            for f in valid:
                try:
                    repo.add_product_image(pid, f.getvalue(), alt or product.name)
                    sent += 1
                except (ImageError, LeadValidationError) as exc:
                    failed.append(f"{f.name}: {exc}")
                except Exception as exc:  # erro inesperado: não expõe detalhes técnicos
                    log.error("Falha no envio de foto: %s", type(exc).__name__)
                    failed.append(f"{f.name}: não foi possível enviar agora.")
        if failed:
            st.error("Algumas fotos não foram enviadas:\n\n" + "\n".join(f"- {m}" for m in failed))
        if sent:
            st.session_state[f"upl_nonce_{pid}"] = _uploader_nonce(pid) + 1
            flash("success", f"{sent} foto(s) enviada(s) para **{product.name}**.")
            if not failed:
                st.rerun()


def render_gallery(repo, product, images: list[dict]) -> None:
    pid = product.id
    if not images:
        st.info("Este produto ainda não tem fotos enviadas. "
                + ("A vitrine usa a imagem padrão." if product.image_path else "A vitrine mostra o card sem foto."))
        return
    st.markdown(f"**Fotos do produto** ({len(images)} de {MAX_IMAGES_PER_PRODUCT})")
    pending = st.session_state.get("img_to_delete")
    for row_start in range(0, len(images), 3):
        cols = st.columns(3)
        for col, img in zip(cols, images[row_start: row_start + 3]):
            with col, st.container(border=True):
                if img.get("url"):
                    st.image(img["url"], width="stretch")
                else:
                    st.warning("Arquivo não encontrado.")
                if img["principal"]:
                    st.badge("Foto principal", icon="⭐", color="primary")
                elif st.button("Tornar principal", key=f"main_{img['id']}", width="stretch"):
                    _run(lambda: repo.set_principal_image(img["id"]), "Foto principal atualizada.")
                if pending == img["id"]:
                    st.caption("Remover esta foto? Não dá para desfazer.")
                    c1, c2 = st.columns(2)
                    if c1.button("Confirmar", key=f"delimg_ok_{img['id']}", type="primary"):
                        st.session_state.pop("img_to_delete", None)
                        _run(lambda: repo.delete_product_image(img["id"]), "Foto removida.")
                    if c2.button("Cancelar", key=f"delimg_no_{img['id']}"):
                        st.session_state.pop("img_to_delete", None)
                        st.rerun()
                elif st.button("Remover", key=f"delimg_{img['id']}", width="stretch"):
                    st.session_state["img_to_delete"] = img["id"]
                    st.rerun()


def _run(action, success: str) -> None:
    try:
        action()
    except (ImageError, LeadValidationError) as exc:
        st.error(str(exc))
    except Exception as exc:
        log.error("Falha ao alterar foto: %s", type(exc).__name__)
        st.error("Não foi possível alterar a foto agora.")
    else:
        flash("success", success)
        st.rerun()


def image_manager(repo, product) -> None:
    try:
        images = repo.list_product_images(product.id)
    except (ImageError, LeadValidationError) as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        log.error("Falha ao listar fotos: %s", type(exc).__name__)
        st.error("Não foi possível carregar as fotos agora.")
        return
    render_gallery(repo, product, images)
    st.divider()
    render_upload(repo, product, images)
