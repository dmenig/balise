from __future__ import annotations

import hashlib

from fastapi import Request, Response


class NotModified(Exception):
    """Raised when `If-None-Match` matches; turned into a bodyless 304 by the app handler."""

    def __init__(self, etag: str, max_age: int) -> None:
        super().__init__(etag)
        self.etag = etag
        self.max_age = max_age


def compute_etag(payload: str | bytes) -> str:
    data = payload.encode() if isinstance(payload, str) else payload
    return f'W/"{hashlib.sha256(data).hexdigest()[:32]}"'


def apply_etag(request: Request, response: Response, payload: str | bytes, max_age: int) -> None:
    """Set `ETag` + `Cache-Control`, and 304 when the client already has this body (docs/08).

    `max_age=0` means *always revalidate*: any resource that embeds a status must not be served
    from a browser cache, or a sailor's own check-in would appear not to have registered. The ETag
    still keeps the revalidation cheap (304, no body).
    """
    etag = compute_etag(payload)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "no-cache" if max_age == 0 else f"public, max-age={max_age}"
    if request.headers.get("if-none-match") == etag:
        raise NotModified(etag, max_age)
