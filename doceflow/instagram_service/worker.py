"""Publicador em execução contínua (ou uma rodada, para agendador/cron).

    python -m instagram_service.worker          # roda sempre, a cada 30 s
    python -m instagram_service.worker --once   # uma rodada e sai

Várias cópias podem rodar juntas: a reserva no banco usa FOR UPDATE SKIP LOCKED.
"""

from __future__ import annotations

import argparse
import logging
import signal
import time

from instagram_service.config import load_config
from instagram_service.graph import InstagramGraph
from instagram_service.publisher import Publisher
from instagram_service.store import Database, Storage

log = logging.getLogger("doceflow.instagram.worker")


def build(cfg=None) -> tuple[Publisher, str]:
    cfg = cfg or load_config()
    graph = InstagramGraph(app_id=cfg.app_id, app_secret=cfg.app_secret, redirect_uri=cfg.redirect_uri,
                           version=cfg.graph_version)
    return Publisher(Database(cfg.db_url), graph, Storage(cfg.supabase_url, cfg.service_key)), cfg.worker_id


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Publicador do Instagram do DoceFlow")
    parser.add_argument("--once", action="store_true", help="uma rodada e sai")
    parser.add_argument("--interval", type=float, default=30.0)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    publisher, worker_id = build()
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    last_refresh = 0.0
    while True:
        if time.monotonic() - last_refresh > 6 * 3600:
            log.info("Tokens renovados: %s", publisher.refresh_tokens())
            last_refresh = time.monotonic()
        result = publisher.run_once(worker_id)
        if any(result.values()):
            log.info("Rodada: %s", result)
        if args.once or stop["now"]:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
