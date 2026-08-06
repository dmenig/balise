from __future__ import annotations

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from balise_api.auth import tokens
from balise_api.auth.dependencies import SessionDep
from balise_api.config import get_settings
from balise_api.models import Contributor
from balise_api.repositories.protocols import DomainError
from balise_api.schemas.reports import MagicLinkIn, MagicLinkOut, SessionOut

router = APIRouter(tags=["auth"], prefix="/auth")
logger = logging.getLogger(__name__)


class InvalidMagicToken(DomainError):
    status_code = 400
    title = "Lien de connexion invalide ou expiré"


@router.post("/magic-link", response_model=MagicLinkOut, status_code=status.HTTP_202_ACCEPTED)
async def request_magic_link(payload: MagicLinkIn) -> MagicLinkOut:
    """No password, ever (docs/08). In prod the token leaves by email only."""
    token = tokens.issue_magic_token(payload.email)
    settings = get_settings()
    if settings.env == "prod":
        logger.info("magic link issued")
        return MagicLinkOut(sent=True)
    return MagicLinkOut(sent=True, magic_token=token)


@router.post("/session", response_model=SessionOut)
async def create_session(token: str, session: SessionDep, response: Response) -> SessionOut:
    try:
        email = tokens.read_token(token, "magic")
    except tokens.InvalidToken as exc:
        raise InvalidMagicToken(str(exc)) from exc
    existing = await session.execute(select(Contributor).where(Contributor.email == email))
    if existing.scalar_one_or_none() is None:
        session.add(Contributor(device_hash=tokens.device_hash(f"account:{email}"), email=email))
        await session.commit()
    response.set_cookie(
        "balise_refresh",
        tokens.issue_refresh_token(email),
        httponly=True,
        samesite="lax",
        secure=get_settings().env in {"staging", "prod"},
        max_age=int(tokens.REFRESH_TTL.total_seconds()),
    )
    return SessionOut(
        access_token=tokens.issue_access_token(email),
        expires_in_seconds=int(tokens.ACCESS_TTL.total_seconds()),
        email=email,
    )
