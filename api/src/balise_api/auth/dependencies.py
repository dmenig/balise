from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from balise_api.auth import tokens
from balise_api.db import get_session
from balise_api.repositories.feeds import SqlFeedRepository
from balise_api.repositories.protocols import (
    ContributorBanned,
    ContributorRef,
    DomainError,
    FeedRef,
)
from balise_api.repositories.sql import SqlContributorRepository

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class MissingCredentials(DomainError):
    status_code = 401
    title = "Authentification requise"


class InvalidCredentials(DomainError):
    status_code = 401
    title = "Jeton invalide"


async def current_contributor(
    session: SessionDep,
    x_device_token: Annotated[str | None, Header(alias="X-Device-Token")] = None,
) -> ContributorRef:
    """Anonymous-by-default identity: one opaque device token, created lazily (docs/06 T2)."""
    if not x_device_token:
        raise MissingCredentials("en-tête X-Device-Token manquant")
    contributor = await SqlContributorRepository(session).get_or_create(
        tokens.device_hash(x_device_token)
    )
    if contributor.banned:
        raise ContributorBanned("contributeur suspendu")
    return contributor


ContributorDep = Annotated[ContributorRef, Depends(current_contributor)]


async def current_feed(
    feed_id: str,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> FeedRef:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise MissingCredentials("en-tête Authorization: Bearer manquant")
    token = authorization.split(" ", 1)[1].strip()
    repo = SqlFeedRepository(session)
    expected = await repo.token_hash(feed_id)
    if not tokens.verify_feed_token(token, expected):
        raise InvalidCredentials("jeton de flux invalide")
    return await repo.get(feed_id)


FeedDep = Annotated[FeedRef, Depends(current_feed)]


async def account_email(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        return None
    try:
        return tokens.read_token(header.split(" ", 1)[1].strip(), "access")
    except tokens.InvalidToken:
        return None
