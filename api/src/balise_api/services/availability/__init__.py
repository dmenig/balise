"""The availability seam (docs/06 §A) and, behind it, the v2 implementation.

v1 imports exactly one thing from here — the provider port and its null implementation, wired in
`main.py`. Everything else in this package (`status.py`, `community.py`, `feeds.py`, `realtime.py`,
`reputation.py`) is the v2 plug-in described in docs/06 §B: it has no v1 callers, and turning it on
is `SqlAvailabilityProvider` plus mounting the availability routers.
"""

from balise_api.services.availability.provider import (
    AvailabilityProvider,
    NullAvailabilityProvider,
    SqlAvailabilityProvider,
)

__all__ = ["AvailabilityProvider", "NullAvailabilityProvider", "SqlAvailabilityProvider"]
