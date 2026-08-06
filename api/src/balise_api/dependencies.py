"""Request-scoped dependencies.

The availability provider *factory* is chosen once at startup (`main.py`); every request just calls
it. Nothing here asks whether availability exists — that question has exactly one answer site
(docs/06 §A/S2).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from balise_api.db import get_session
from balise_api.services.availability import AvailabilityProvider, NullAvailabilityProvider


def availability_provider(
    request: Request, session: Annotated[AsyncSession, Depends(get_session)]
) -> AvailabilityProvider:
    factory = getattr(request.app.state, "availability_provider_factory", NullAvailabilityProvider)
    provider: AvailabilityProvider = factory(session)
    return provider


AvailabilityDep = Annotated[AvailabilityProvider, Depends(availability_provider)]
