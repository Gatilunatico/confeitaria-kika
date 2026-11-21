"""Conexão oficial com o Instagram (OAuth da Meta). Rodar no servidor:

    uvicorn instagram_service.app:app --port 8010      (de dentro de doceflow/)

1. GET /v1/instagram/conexao (com o login da dona): devolve o link da página de autorização da
   Meta, com um "state" aleatório de uso único que vale 10 minutos.
2. A dona autoriza no site da Meta. A Meta redireciona para /v1/instagram/callback.
3. O serviço confere o state, troca o código pelo token (com o segredo do app, que só existe
   aqui), troca por um token de 60 dias, confere se a conta é profissional e guarda no Vault.
"""

from __future__ import annotations

import html
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, Query
from fastapi.responses import HTMLResponse

from api import errors
from api.auth import resolve_admin
from instagram_service.config import InstagramConfig, load_config
from instagram_service.graph import GraphError, InstagramGraph
from instagram_service.store import Database

log = logging.getLogger("doceflow.instagram.app")
STATE_TTL = timedelta(minutes=10)
PROFESSIONAL = {"business", "media_creator", "creator"}


def page(title: str, message: str, ok: bool) -> HTMLResponse:
    color = "#5C3317" if ok else "#B3261E"
    body = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title></head>
<body style="font-family:sans-serif;background:#FDE8EC;color:#5C3317;display:flex;min-height:100vh;
align-items:center;justify-content:center;margin:0"><main style="background:#fff;border-radius:20px;
padding:28px;max-width:420px;margin:16px;text-align:center"><h1 style="color:{color};font-size:1.4rem">
{html.escape(title)}</h1><p>{html.escape(message)}</p><p>Pode fechar esta página e voltar ao app DoceFlow.</p>
</main></body></html>"""
    return HTMLResponse(body, status_code=200 if ok else 400,
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                                 "X-Content-Type-Options": "nosniff"})


def create_app(cfg: InstagramConfig | None = None, db: Database | None = None, graph: InstagramGraph | None = None,
               admin_resolver=resolve_admin) -> FastAPI:
    app = FastAPI(title="DoceFlow · conexão com o Instagram", docs_url=None, redoc_url=None, openapi_url=None)
    errors.install(app)
    state = {"cfg": cfg, "db": db, "graph": graph}

    def deps():
        if state["cfg"] is None:
            state["cfg"] = load_config()
        c = state["cfg"]
        if state["db"] is None:
            state["db"] = Database(c.db_url)
        if state["graph"] is None:
            state["graph"] = InstagramGraph(app_id=c.app_id, app_secret=c.app_secret, redirect_uri=c.redirect_uri,
                                            version=c.graph_version)
        return state["cfg"], state["db"], state["graph"]

    @app.get("/v1/saude")
    def saude():
        return {"status": "ok"}

    @app.get("/v1/instagram/conexao")
    def conexao(authorization: str | None = Header(default=None)):
        ctx = admin_resolver(authorization)  # token conferido no Supabase + perfil de administradora
        c, db_, g = deps()
        nonce = secrets.token_urlsafe(32)
        db_.create_state(nonce, ctx.store.id, ctx.user_id, STATE_TTL)
        return {"url": g.authorize_url(nonce, c.scopes), "expira_em_segundos": int(STATE_TTL.total_seconds())}

    @app.get("/v1/instagram/callback", response_class=HTMLResponse)
    def callback(code: str | None = Query(default=None, max_length=2048),
                 state_: str | None = Query(default=None, alias="state", max_length=200),
                 error: str | None = Query(default=None, max_length=200)):
        _, db_, g = deps()
        if error or not code:
            return page("Conexão não concluída", "A autorização foi cancelada na página da Meta.", False)
        claimed = db_.consume_state(state_ or "") if state_ else None
        if not claimed:
            return page("Link vencido", "Este link de conexão já foi usado ou venceu. Toque em Conectar de novo no app.",
                        False)
        store_id, _user = claimed
        try:
            short = g.exchange_code(code)
            long = g.long_lived(short.token)
            me = g.me(long.token)
        except GraphError as e:
            log.warning("Conexão recusada pela Meta: %s", e.label)
            return page("Não foi possível conectar", "A Meta recusou a autorização. Tente de novo em alguns minutos.",
                        False)
        account_type = str(me.get("account_type") or "").lower()
        if account_type not in PROFESSIONAL:
            return page("Conta não elegível",
                        "Só contas profissionais (Empresa ou Criador de conteúdo) podem publicar pela API da Meta. "
                        "Mude o tipo da conta no app do Instagram e conecte de novo.", False)
        expires = datetime.now(timezone.utc) + timedelta(seconds=long.expires_in or 60 * 24 * 3600)
        db_.save_connection(store_id, str(me.get("user_id") or short.user_id or ""), str(me.get("username") or ""),
                            account_type, long.token, expires)
        log.info("Instagram conectado para uma confeitaria")
        return page("Instagram conectado!", f"Conta @{me.get('username', '')} conectada ao DoceFlow.", True)

    return app


app = create_app()
