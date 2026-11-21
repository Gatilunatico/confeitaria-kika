"""Formato único de erro da API: {"erro": {"codigo": "...", "mensagem": "..."}}.

As mensagens podem ir direto para a tela do app (português, sem detalhes técnicos). Nada de
token, chave, SQL ou stack trace na resposta. O log registra só o tipo do erro.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("doceflow.api")


class ApiError(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str, headers: dict | None = None):
        super().__init__(codigo)
        self.status, self.codigo, self.mensagem, self.headers = status, codigo, mensagem, headers


def body(codigo: str, mensagem: str, **extra) -> dict:
    return {"erro": {"codigo": codigo, "mensagem": mensagem, **extra}}


HTTP_DEFAULTS = {
    404: ("nao_encontrado", "Endereço não encontrado."),
    405: ("metodo_nao_permitido", "Operação não permitida neste endereço."),
}


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(body(exc.codigo, exc.mensagem), status_code=exc.status, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        # Só o campo e o problema: o valor enviado NÃO volta na resposta (pode ser dado pessoal).
        campos = [{"campo": ".".join(str(p) for p in e.get("loc", ())[1:]) or "corpo", "problema": e.get("type", "")}
                  for e in exc.errors()]
        return JSONResponse(body("dados_invalidos", "Confira os dados enviados.", campos=campos), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        codigo, mensagem = HTTP_DEFAULTS.get(exc.status_code, ("erro_http", "Não foi possível concluir o pedido."))
        return JSONResponse(body(codigo, mensagem), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception):
        log.error("Erro inesperado na API: %s", type(exc).__name__)
        return JSONResponse(body("erro_interno", "Algo deu errado. Tente novamente em instantes."), status_code=500)
