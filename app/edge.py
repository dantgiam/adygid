"""Входной ASGI-слой: голый домен → www и ответы на HEAD.

1. Голый adygid.ru получает 301 на https://www.adygid.ru с тем же путём и query.
2. HEAD обслуживается как GET без тела (FastAPI отвечал 405). Внутрь приложения запрос уходит как GET, поэтому мидлвари, которые на не-GET сбрасывают кэш главной, на HEAD не срабатывают.
"""
from __future__ import annotations

CANONICAL_ORIGIN = "https://www.adygid.ru"
REDIRECT_HOSTS = frozenset({"adygid.ru"})


def _host(scope) -> str:
    for name, value in scope.get("headers") or ():
        if name == b"host":
            host = value.decode("latin-1").strip().lower()
            if host.startswith("["):
                return host.split("]")[0] + "]"
            return host.split(":")[0].rstrip(".")
    return ""


class EdgeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        if _host(scope) in REDIRECT_HOSTS:
            path = scope.get("raw_path") or scope.get("path", "/").encode("utf-8")
            if isinstance(path, str):
                path = path.encode("utf-8")
            path = path.split(b"?", 1)[0]
            location = CANONICAL_ORIGIN.encode() + (path or b"/")
            query = scope.get("query_string") or b""
            if query:
                location += b"?" + query
            await send({
                "type": "http.response.start",
                "status": 301,
                "headers": [
                    (b"location", location),
                    (b"content-length", b"0"),
                    (b"cache-control", b"public, max-age=86400"),
                ],
            })
            await send({"type": "http.response.body", "body": b""})
            return

        if scope.get("method") == "HEAD":
            scope = dict(scope, method="GET")

            async def send_headers_only(message):
                if message["type"] == "http.response.body":
                    if message.get("more_body"):
                        return
                    message = {"type": "http.response.body", "body": b""}
                await send(message)

            return await self.app(scope, receive, send_headers_only)

        return await self.app(scope, receive, send)
