"""Tokens. No PII in a device token, feed tokens hashed at rest, never logged (docs/08, docs/12)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from jose import JWTError, jwt

from balise_api.config import get_settings

ALGORITHM = "HS256"
ACCESS_TTL = timedelta(minutes=15)
MAGIC_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)
TokenPurpose = Literal["access", "magic", "refresh"]


class InvalidToken(ValueError):
    pass


def issue_device_token() -> str:
    """Opaque, PII-free, stored in localStorage by the client."""
    return f"dev_{secrets.token_urlsafe(32)}"


def device_hash(token: str) -> str:
    """Salted hash; the salt rotates every 6 months (docs/04 §4)."""
    salt = get_settings().device_token_salt.encode()
    return hashlib.sha256(salt + token.encode()).hexdigest()


def feed_token_hash(token: str) -> str:
    salt = get_settings().secret_key.encode()
    return hashlib.sha256(salt + token.encode()).hexdigest()


def verify_feed_token(token: str, expected_hash: str) -> bool:
    return hmac.compare_digest(feed_token_hash(token), expected_hash)


def issue_feed_token(feed_id: str) -> tuple[str, str]:
    token = f"mbfs_{feed_id.replace('.', '-')}_{secrets.token_urlsafe(24)}"
    return token, feed_token_hash(token)


def _encode(subject: str, purpose: TokenPurpose, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "purpose": purpose,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    token: str = jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITHM)
    return token


def issue_magic_token(email: str) -> str:
    return _encode(email, "magic", MAGIC_TTL)


def issue_access_token(email: str) -> str:
    return _encode(email, "access", ACCESS_TTL)


def issue_refresh_token(email: str) -> str:
    return _encode(email, "refresh", REFRESH_TTL)


def read_token(token: str, purpose: TokenPurpose) -> str:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise InvalidToken(str(exc)) from exc
    if payload.get("purpose") != purpose:
        raise InvalidToken(f"expected a {purpose} token")
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise InvalidToken("missing subject")
    return subject
