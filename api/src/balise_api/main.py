from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from balise_api import attribution, cache
from balise_api.config import get_settings
from balise_api.db import dispose_engine
from balise_api.http.etag import NotModified
from balise_api.http.problems import PROBLEM_MEDIA_TYPE
from balise_api.repositories.protocols import DomainError
from balise_api.routers import (
    auth,
    availability,
    harbours,
    issues,
    meta,
    navaids,
    opendata,
    spots,
    tiles,
)
from balise_api.schemas.common import ProblemDetail
from balise_api.services.availability import NullAvailabilityProvider

API_PREFIX = "/v1"
logger = logging.getLogger(__name__)

#: The one and only availability switch (docs/06 §A/S2, docs/11). A seam test greps for the env-var
#: name across `api/src` and requires exactly one hit — the line below. That single reference is
#: what stops "pluggable" from decaying into forty conditionals.
AVAILABILITY_ENABLED = os.environ.get("FEATURE_AVAILABILITY", "false").strip().lower() in {
    "1",
    "true",
    "yes",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    yield
    await cache.close_redis()
    await dispose_engine()


def _problem(status_code: int, title: str, detail: str | None, request: Request) -> JSONResponse:
    payload = ProblemDetail(
        title=title, status=status_code, detail=detail, instance=str(request.url.path)
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        media_type=PROBLEM_MEDIA_TYPE,
    )


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Balise API",
        version="0.1.0",
        description=(
            "Cartographie des mouillages, des places de port et du balisage en France. "
            f"{attribution.DISCLAIMER} — {attribution.BLOCK}"
        ),
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        lifespan=lifespan,
    )
    # The availability provider is chosen exactly once, here (docs/06 §A/S2). Everything downstream
    # calls the port and serialises whatever it returns — `{}` in v1, real statuses in v2.
    app.state.availability_provider_factory = NullAvailabilityProvider
    app.state.availability_enabled = AVAILABILITY_ENABLED

    app.add_middleware(GZipMiddleware, minimum_size=800)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["ETag", "Retry-After"],
    )

    @app.middleware("http")
    async def rate_limit(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """60 req/min per IP, tiles counted separately (docs/08). CDN limits sit in front."""
        is_tile = request.url.path.startswith(f"{API_PREFIX}/tiles/")
        limit = (
            settings.rate_limit_tiles_per_min if is_tile else settings.rate_limit_anonymous_per_min
        )
        client = request.client
        identity = client.host if client else "unknown"
        bucket = f"rl:tiles:{identity}:{limit}" if is_tile else f"rl:{identity}:{limit}"
        if await cache.hit_rate_limit(bucket, limit):
            refused = _problem(429, "Trop de requêtes", f"limite {limit}/min", request)
            refused.headers["Retry-After"] = "60"
            return refused
        response = await call_next(request)
        response.headers.setdefault("X-Balise-Disclaimer", "planification-uniquement")
        return response

    @app.exception_handler(NotModified)
    async def not_modified(request: Request, exc: NotModified) -> Response:
        cache_control = "no-cache" if exc.max_age == 0 else f"public, max-age={exc.max_age}"
        return Response(status_code=304, headers={"ETag": exc.etag, "Cache-Control": cache_control})

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return _problem(exc.status_code, exc.title, str(exc), request)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(422, "Requête invalide", str(exc.errors()), request)

    for router in (
        meta.router,
        spots.router,
        harbours.router,
        navaids.router,
        tiles.router,
        issues.router,
        auth.router,
        opendata.router,
    ):
        app.include_router(router, prefix=API_PREFIX)

    if app.state.availability_enabled:
        _enable_availability(app)
    else:
        # 🔌 Specified and refusing: the v2 surface exists in the schema and returns 501 (docs/08).
        app.include_router(availability.router, prefix=API_PREFIX)

    app.include_router(meta.router)  # unprefixed /health and /ready for the prober
    return app


def _enable_availability(app: FastAPI) -> None:
    """v2 wiring, kept in one function so M3 is a switch and the rollback is a switch back.

    Imported lazily so v1 never even loads the availability implementation.
    """
    from balise_api.routers import feeds, reports, stream
    from balise_api.services.availability import SqlAvailabilityProvider

    logger.warning("availability enabled: serving live status (docs/06 §B)")
    app.state.availability_provider_factory = SqlAvailabilityProvider  # the M3 one-liner
    for router in (reports.router, feeds.router, stream.router):
        app.include_router(router, prefix=API_PREFIX)


app = create_app()
