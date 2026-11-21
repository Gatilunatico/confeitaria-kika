"""Aplicação FastAPI. Rodar localmente:

    uvicorn api.main:app --port 8000        (de dentro da pasta doceflow/)

Variáveis: SUPABASE_URL, SUPABASE_KEY (publishable), STORE_SLUG e PUBLIC_APP_URL — as mesmas do
painel. NUNCA configure a chave service_role aqui: a API não precisa dela.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from api import errors
from api.auth import AdminContext, require_admin
from api.marketing import router as marketing_router

API_VERSION = "1.0.0"
MAX_BODY_BYTES = 64 * 1024  # os pedidos são JSON pequenos; imagens não passam por aqui


def create_app() -> FastAPI:
    app = FastAPI(title="DoceFlow API (app da confeiteira)", version=API_VERSION,
                  docs_url="/v1/docs", redoc_url=None, openapi_url="/v1/openapi.json")
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
    def instagram_status(_: AdminContext = Depends(require_admin)):
        """A publicação automática foi adiada (decisão de 21/11/2026, depende da confeiteira)."""
        return {
            "publicacao_automatica": False,
            "motivo": "A publicação automática no Instagram ainda não foi ativada.",
            "alternativa": "Baixe a arte, copie a legenda e publique pelo app do Instagram.",
        }

    app.include_router(marketing_router)
    return app


app = create_app()
