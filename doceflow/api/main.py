"""Aplicação FastAPI. Rodar localmente:

    uvicorn api.main:app --port 8000        (de dentro da pasta doceflow/)

Variáveis: SUPABASE_URL, SUPABASE_KEY (publishable), STORE_SLUG e PUBLIC_APP_URL — as mesmas do
painel. NUNCA configure a chave service_role aqui: a API não precisa dela.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from api import errors
from api.auth import AdminContext, require_admin
from api.marketing import router as marketing_router

API_VERSION = "1.0.0"
MAX_BODY_BYTES = 64 * 1024  # os pedidos são JSON pequenos; imagens não passam por aqui


def create_app() -> FastAPI:
    # Documentação interativa só quando pedida (API_DOCS=1): em produção não expõe o mapa da API.
    docs = (os.getenv("API_DOCS") or "").strip() == "1"
    app = FastAPI(title="DoceFlow API (app da confeiteira)", version=API_VERSION,
                  docs_url="/v1/docs" if docs else None, redoc_url=None,
                  openapi_url="/v1/openapi.json" if docs else None)
    errors.install(app)

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        size = request.headers.get("content-length")
        if size is not None and (not size.isdigit() or int(size) > MAX_BODY_BYTES):
            return JSONResponse(errors.body("corpo_muito_grande", "Pedido grande demais."), status_code=413)
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/v1/saude", tags=["sistema"])
    def saude():
        """Sem login. Não revela configuração nem versão de bibliotecas."""
        return {"status": "ok", "versao": API_VERSION}

    @app.get("/v1/eu", tags=["sistema"])
    def eu(ctx: AdminContext = Depends(require_admin)):
        """Quem está logado e qual confeitaria administra (confirma o login no app)."""
        return {"usuario_id": ctx.user_id,
                "confeitaria": {"id": ctx.store.id, "slug": ctx.store.slug, "nome": ctx.store.name}}

    @app.get("/v1/instagram/status", tags=["instagram"])
    def instagram_status(ctx: AdminContext = Depends(require_admin)):
        """Estado da conta (sem token). A conexão e a publicação ficam no serviço do Instagram
        (doceflow/instagram_service), separado desta API."""
        try:
            res = (ctx.client.table("instagram_accounts").select("username,status,account_type,token_expira_em")
                   .eq("confeitaria_id", ctx.store.id).limit(1).execute())
            conta = res.data[0] if res.data else None
        except Exception:
            conta = None
        conectado = bool(conta and conta.get("status") == "conectado")
        return {
            "publicacao_automatica": conectado,
            "conta": conta,
            "motivo": None if conectado else "O Instagram não está conectado (ou a conexão precisa ser refeita).",
            "alternativa": "Baixe a arte, copie a legenda e publique pelo app do Instagram.",
        }

    app.include_router(marketing_router)
    return app


app = create_app()
