"""RFC 9457 problem documents that are part of the contract (docs/08)."""

from __future__ import annotations

from fastapi.responses import JSONResponse

PROBLEM_MEDIA_TYPE = "application/problem+json"

AVAILABILITY_NOT_ENABLED = {
    "type": "https://balise.fr/problems/availability-not-enabled",
    "title": "Availability is not enabled",
    "status": 501,
    "detail": "Live availability is not part of this release. See /a-propos/donnees.",
}


def availability_not_enabled() -> JSONResponse:
    """Specified-and-refusing beats undefined (docs/06 §A/S3).

    A client written against v1 gets a documented, machine-readable refusal on the exact URL that
    will start working in v2 — no 404 to interpret, no breaking change later.
    """
    return JSONResponse(
        status_code=501, content=AVAILABILITY_NOT_ENABLED, media_type=PROBLEM_MEDIA_TYPE
    )
