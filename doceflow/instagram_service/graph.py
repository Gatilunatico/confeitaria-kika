"""Cliente da API OFICIAL do Instagram (Instagram API com login do Instagram, graph.instagram.com).

Documentação da Meta:
- Autorização: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login
- Publicação:  https://developers.facebook.com/docs/instagram-platform/content-publishing

O token vai no cabeçalho Authorization (não na URL), e nenhum log inclui token ou URL com token.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

log = logging.getLogger("doceflow.instagram.graph")

AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
GRAPH = "https://graph.instagram.com"

AUTH_CODES = {102, 190, 463, 467}  # token inválido, vencido ou revogado
RATE_CODES = {4, 9, 17, 32, 613}  # limites de chamadas
PUBLISH_LIMIT_SUBCODE = 2207042  # limite de publicações em 24 h


class GraphError(RuntimeError):
    """Erro devolvido pela Meta (ou de rede), já classificado."""

    def __init__(self, message: str, *, code: int | None = None, subcode: int | None = None,
                 status: int | None = None, transient: bool = False, auth: bool = False, rate_limited: bool = False):
        super().__init__(message)
        self.code, self.subcode, self.status = code, subcode, status
        self.transient, self.auth, self.rate_limited = transient, auth, rate_limited

    @property
    def label(self) -> str:
        if self.code is None:
            return f"http_{self.status}" if self.status else "rede"
        return f"meta_{self.code}" + (f"_{self.subcode}" if self.subcode else "")


def _classify(resp: httpx.Response) -> GraphError:
    try:
        err = resp.json().get("error") or {}
    except ValueError:
        err = {}
    code = err.get("code")
    sub = err.get("error_subcode")
    msg = str(err.get("error_user_msg") or err.get("message") or f"HTTP {resp.status_code}")[:300]
    auth = code in AUTH_CODES
    rate = code in RATE_CODES or sub == PUBLISH_LIMIT_SUBCODE
    transient = bool(err.get("is_transient")) or resp.status_code >= 500 or rate
    return GraphError(msg, code=code, subcode=sub, status=resp.status_code,
                      transient=transient and not auth, auth=auth, rate_limited=rate)


@dataclass
class TokenInfo:
    token: str
    expires_in: int | None
    user_id: str | None = None


class InstagramGraph:
    def __init__(self, *, app_id: str, app_secret: str, redirect_uri: str, version: str = "v23.0",
                 client: httpx.Client | None = None):
        self.app_id, self._secret, self.redirect_uri, self.version = app_id, app_secret, redirect_uri, version
        self.http = client or httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))

    # ---------------------------------------------------------------- chamadas
    def _call(self, method: str, url: str, *, token: str | None = None, **kw) -> dict:
        headers = kw.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = self.http.request(method, url, headers=headers, **kw)
        except httpx.TimeoutException as exc:
            raise GraphError("Tempo esgotado falando com a Meta.", transient=True) from exc
        except httpx.HTTPError as exc:
            raise GraphError("Falha de rede falando com a Meta.", transient=True) from exc
        if resp.status_code >= 400:
            err = _classify(resp)
            log.warning("Meta recusou %s %s: %s", method, url.split("?")[0].rsplit("/", 1)[-1], err.label)
            raise err
        try:
            return resp.json()
        except ValueError as exc:
            raise GraphError("Resposta inválida da Meta.", status=resp.status_code, transient=True) from exc

    def _graph(self, path: str) -> str:
        return f"{GRAPH}/{self.version}/{path.lstrip('/')}"

    # ---------------------------------------------------------------- autorização (OAuth)
    def authorize_url(self, state: str, scopes: tuple[str, ...]) -> str:
        return AUTHORIZE_URL + "?" + urlencode({
            "client_id": self.app_id, "redirect_uri": self.redirect_uri, "response_type": "code",
            "scope": ",".join(scopes), "state": state,
        })

    def exchange_code(self, code: str) -> TokenInfo:
        data = self._call("POST", TOKEN_URL, data={
            "client_id": self.app_id, "client_secret": self._secret, "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri, "code": code.split("#")[0],
        })
        item = (data.get("data") or [data])[0]
        if not item.get("access_token"):
            raise GraphError("A Meta não devolveu o token.")
        return TokenInfo(item["access_token"], None, str(item.get("user_id") or "") or None)

    def long_lived(self, short_token: str) -> TokenInfo:
        data = self._call("GET", f"{GRAPH}/access_token",
                          params={"grant_type": "ig_exchange_token", "client_secret": self._secret,
                                  "access_token": short_token})
        return TokenInfo(data["access_token"], int(data.get("expires_in") or 0) or None)

    def refresh(self, token: str) -> TokenInfo:
        data = self._call("GET", f"{GRAPH}/refresh_access_token",
                          params={"grant_type": "ig_refresh_token", "access_token": token})
        return TokenInfo(data["access_token"], int(data.get("expires_in") or 0) or None)

    def me(self, token: str) -> dict:
        return self._call("GET", self._graph("me"), token=token, params={"fields": "user_id,username,account_type"})

    # ---------------------------------------------------------------- publicação
    def create_container(self, ig_user_id: str, token: str, image_url: str, caption: str, story: bool) -> str:
        params = {"image_url": image_url}
        if story:
            params["media_type"] = "STORIES"
        elif caption:
            params["caption"] = caption
        data = self._call("POST", self._graph(f"{ig_user_id}/media"), token=token, data=params)
        return str(data["id"])

    def container_status(self, container_id: str, token: str) -> str:
        data = self._call("GET", self._graph(container_id), token=token, params={"fields": "status_code"})
        return str(data.get("status_code") or "")

    def publish(self, ig_user_id: str, token: str, container_id: str) -> str:
        data = self._call("POST", self._graph(f"{ig_user_id}/media_publish"), token=token,
                          data={"creation_id": container_id})
        media_id = str(data.get("id") or "")
        if not media_id:
            raise GraphError("A Meta não devolveu o id da publicação.", transient=False)
        return media_id

    def permalink(self, media_id: str, token: str) -> str | None:
        data = self._call("GET", self._graph(media_id), token=token, params={"fields": "permalink"})
        link = data.get("permalink")
        return link if isinstance(link, str) and link.startswith("https://") else None

    def recent_media(self, ig_user_id: str, token: str, limit: int = 10) -> list[dict]:
        data = self._call("GET", self._graph(f"{ig_user_id}/media"), token=token,
                          params={"fields": "id,caption,timestamp,permalink", "limit": str(limit)})
        return list(data.get("data") or [])

    def publishing_quota(self, ig_user_id: str, token: str) -> tuple[int, int] | None:
        """(usadas, limite) nas últimas 24 h, ou None se a Meta não informar."""
        data = self._call("GET", self._graph(f"{ig_user_id}/content_publishing_limit"), token=token,
                          params={"fields": "quota_usage,config"})
        rows = data.get("data") or []
        if not rows:
            return None
        used = int(rows[0].get("quota_usage") or 0)
        total = int(((rows[0].get("config") or {}).get("quota_total")) or 100)
        return used, total
