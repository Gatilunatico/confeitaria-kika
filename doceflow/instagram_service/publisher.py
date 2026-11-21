"""Publicador: leva cada item da fila até o Instagram pela API oficial, sem duplicar e sem
dar como publicado o que a Meta não confirmou.

Fluxo da Meta (2 passos): criar o "container" da mídia → esperar FINISHED → media_publish.
O id do container é salvo ANTES de publicar. Se o serviço cair no meio, a próxima rodada
pergunta à Meta o estado do container:
- FINISHED: ainda não publicou → publica;
- PUBLISHED: já publicou → procura a mídia nas publicações recentes; sem certeza, marca
  "verificar" para conferência manual (nunca publica de novo).
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from instagram_service.graph import GraphError, InstagramGraph
from instagram_service.store import Database, Publication, Storage

log = logging.getLogger("doceflow.instagram.publisher")

POLL_TRIES, POLL_SECONDS = 6, 5.0
RATE_WAIT = timedelta(hours=1)


def backoff(tentativas: int) -> timedelta:
    """2, 4, 8... minutos (até 1 h) entre tentativas automáticas."""
    return timedelta(minutes=min(60, 2 ** max(1, tentativas)))


class Publisher:
    def __init__(self, db: Database, graph: InstagramGraph, storage: Storage,
                 sleep: Callable[[float], None] = time.sleep, poll_tries: int = POLL_TRIES):
        self.db, self.graph, self.storage, self.sleep, self.poll_tries = db, graph, storage, sleep, poll_tries

    # ---------------------------------------------------------------- rodada
    def run_once(self, worker_id: str, limit: int = 5) -> dict[str, int]:
        result = {"publicado": 0, "agendado": 0, "falhou": 0, "verificar": 0}
        for pub in self.db.reserve(worker_id, limit):
            outcome = self.process(pub)
            result[outcome] = result.get(outcome, 0) + 1
        return result

    def process(self, pub: Publication) -> str:
        try:
            return self._process(pub)
        except GraphError as e:
            return self._graph_failure(pub, e)
        except Exception as e:  # noqa: BLE001  (nunca deixa o item preso em "publicando")
            log.error("Erro inesperado publicando %s: %s", pub.id, type(e).__name__)
            return self.db.fail(pub.id, "erro_interno", "Erro interno do serviço. Nova tentativa automática.",
                                True, backoff(pub.tentativas))

    def _process(self, pub: Publication) -> str:
        account = self.db.token(pub.confeitaria_id)
        if account is None:
            return self.db.fail(pub.id, "instagram_desconectado",
                                "O Instagram não está conectado. Conecte de novo no app.", False, timedelta(0))
        ig_user, token, _ = account

        if pub.ig_container_id:  # retomada depois de queda ou de nova tentativa
            status = self.graph.container_status(pub.ig_container_id, token)
            if status == "PUBLISHED":
                return self._reconcile(pub, ig_user, token)
            if status == "FINISHED":
                return self._publish(pub, ig_user, token, pub.ig_container_id)
            if status == "IN_PROGRESS":
                return self._wait_and_publish(pub, ig_user, token, pub.ig_container_id)
            self.db.log(pub.id, "container_descartado", status or "sem status")  # ERROR/EXPIRED: cria outro

        url = self.storage.jpeg_url(pub.confeitaria_id, pub.id, pub.imagem_path)
        container = self.graph.create_container(ig_user, token, url, pub.legenda, story=pub.formato == "story")
        self.db.save_container(pub.id, container)
        return self._wait_and_publish(pub, ig_user, token, container)

    def _wait_and_publish(self, pub: Publication, ig_user: str, token: str, container: str) -> str:
        for i in range(self.poll_tries):
            status = self.graph.container_status(container, token)
            if status == "FINISHED":
                return self._publish(pub, ig_user, token, container)
            if status == "PUBLISHED":
                return self._reconcile(pub, ig_user, token)
            if status in ("ERROR", "EXPIRED"):
                return self.db.fail(pub.id, f"container_{status.lower()}",
                                    "A Meta não aceitou a imagem (formato ou tamanho). Gere a arte de novo.",
                                    status == "EXPIRED", backoff(pub.tentativas))
            if i < self.poll_tries - 1:
                self.sleep(POLL_SECONDS)
        return self.db.fail(pub.id, "midia_processando", "A Meta ainda está processando a imagem.", True,
                            timedelta(minutes=2))

    def _publish(self, pub: Publication, ig_user: str, token: str, container: str) -> str:
        quota = self.graph.publishing_quota(ig_user, token)
        if quota and quota[0] >= quota[1]:
            return self.db.fail(pub.id, "limite_diario", "Limite diário de publicações da Meta atingido.", True,
                                RATE_WAIT)
        self.db.log(pub.id, "publicacao_pedida", container)
        try:
            media_id = self.graph.publish(ig_user, token, container)
        except GraphError as e:
            if e.transient and e.code is None:
                # rede caiu DEPOIS de pedir: a Meta pode ter publicado. Pergunta antes de repetir.
                if self.graph.container_status(container, token) == "PUBLISHED":
                    return self._reconcile(pub, ig_user, token)
            raise
        permalink = None
        try:
            permalink = self.graph.permalink(media_id, token)
        except GraphError:
            pass  # o link é só conveniência; a publicação já foi confirmada pelo id
        self.db.conclude(pub.id, media_id, permalink)
        log.info("Publicação %s concluída no Instagram", pub.id)
        return "publicado"

    def _reconcile(self, pub: Publication, ig_user: str, token: str) -> str:
        """Container já publicado: acha a mídia pela legenda e horário; sem certeza, pede conferência."""
        since = (pub.bloqueado_em or datetime.now(timezone.utc)) - timedelta(hours=2)
        if pub.legenda.strip():
            for m in self.graph.recent_media(ig_user, token):
                ts = _parse_ts(m.get("timestamp"))
                if (m.get("caption") or "").strip() == pub.legenda.strip() and ts and ts >= since:
                    self.db.conclude(pub.id, str(m["id"]), m.get("permalink"))
                    return "publicado"
        self.db.mark_verify(pub.id, "A Meta indica que a mídia foi publicada, mas não foi possível confirmar qual. "
                                    "Confira no Instagram antes de publicar de novo.")
        return "verificar"

    def _graph_failure(self, pub: Publication, e: GraphError) -> str:
        if e.auth:
            self.db.account_error(pub.confeitaria_id, "Autorização do Instagram vencida ou revogada.")
            return self.db.fail(pub.id, e.label, "A autorização do Instagram venceu ou foi revogada. "
                                                 "Conecte de novo no app.", False, timedelta(0))
        if e.rate_limited:
            return self.db.fail(pub.id, e.label, "Limite de uso da Meta atingido. Nova tentativa mais tarde.",
                                True, RATE_WAIT)
        if e.transient:
            return self.db.fail(pub.id, e.label, "Instabilidade na Meta ou na rede. Nova tentativa automática.",
                                True, backoff(pub.tentativas))
        return self.db.fail(pub.id, e.label, f"A Meta recusou: {e}"[:500], False, timedelta(0))

    # ---------------------------------------------------------------- token
    def refresh_tokens(self, before: timedelta = timedelta(days=10)) -> int:
        """Renova tokens de 60 dias antes de vencer (a Meta aceita após 24 h de emitido)."""
        done = 0
        for store in self.db.accounts_to_refresh(before):
            acc = self.db.token(store)
            if not acc:
                continue
            ig_user, token, _ = acc
            try:
                info = self.graph.refresh(token)
                me = self.graph.me(info.token)
            except GraphError as e:
                if e.auth:
                    self.db.account_error(store, "Autorização do Instagram vencida. Conecte de novo no app.")
                continue
            expires = datetime.now(timezone.utc) + timedelta(seconds=info.expires_in or 60 * 24 * 3600)
            self.db.save_connection(store, str(me.get("user_id") or ig_user), me.get("username") or "",
                                    str(me.get("account_type") or ""), info.token, expires)
            done += 1
        return done


def _parse_ts(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.strptime(str(v), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        try:
            return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        except ValueError:
            return None
