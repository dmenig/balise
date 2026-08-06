"""Repository interfaces + the DTOs that cross them.

Production implementations live in `repositories/sql.py`; tests use the in-memory ones in
`api/tests/inmemory.py`. Both raise the same domain exceptions (docs/13).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from balise_api.domain.enums import ReportKind, SourceKind, SpotKind, SpotState
from balise_api.domain.observation import DerivedFieldStatus, DerivedStatus, ObservationInput


class DomainError(Exception):
    """Base class for errors that map to a client-visible problem+json response."""

    status_code = 400
    title = "Requête invalide"


class SpotNotFound(DomainError):
    status_code = 404
    title = "Mouillage inconnu"


class FieldNotFound(DomainError):
    status_code = 404
    title = "Zone inconnue"


class HarbourNotFound(DomainError):
    status_code = 404
    title = "Port inconnu"


class NavAidNotFound(DomainError):
    status_code = 404
    title = "Amer inconnu"


class FeedNotFound(DomainError):
    status_code = 404
    title = "Flux inconnu"


class ContributorBanned(DomainError):
    status_code = 403
    title = "Contributeur suspendu"


class RateLimited(DomainError):
    status_code = 429
    title = "Trop de signalements"


class FeatureDisabled(DomainError):
    status_code = 503
    title = "Fonctionnalité désactivée"


@dataclass(frozen=True, slots=True)
class SpotRef:
    id: int
    kind: SpotKind
    lon: float
    lat: float
    field_id: int | None = None
    harbour_id: int | None = None
    code: str | None = None


@dataclass(frozen=True, slots=True)
class FieldRef:
    id: int
    kind: SpotKind
    capacity: int | None
    harbour_id: int | None = None


@dataclass(frozen=True, slots=True)
class ContributorRef:
    id: int
    device_hash: str
    reputation: float
    banned: bool


@dataclass(frozen=True, slots=True)
class NewObservation:
    state: SpotState
    source_kind: SourceKind
    report_kind: ReportKind
    observed_at: datetime
    confidence: float
    spot_id: int | None = None
    field_id: int | None = None
    free_count: int | None = None
    source_ref: str | None = None
    contributor_id: int | None = None
    idempotency_key: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StoredObservation:
    id: int
    record: NewObservation


@dataclass(frozen=True, slots=True)
class FeedRef:
    id: str
    harbour_id: int
    kind: SourceKind
    trust: float
    ttl_seconds: int
    active: bool
    last_seen_at: datetime | None = None


class SpotRepository(Protocol):
    async def get(self, spot_id: int) -> SpotRef: ...

    async def distance_m(self, spot_id: int, lon: float, lat: float) -> float: ...


class FieldRepository(Protocol):
    async def get(self, field_id: int) -> FieldRef: ...

    async def get_by_external(self, feed_id: str, external_id: str) -> FieldRef: ...


class ObservationRepository(Protocol):
    async def add(self, record: NewObservation) -> StoredObservation: ...

    async def find_by_idempotency_key(self, key: str) -> StoredObservation | None: ...

    async def recent_for_spot(self, spot_id: int, since: datetime) -> list[ObservationInput]: ...

    async def recent_for_field(self, field_id: int, since: datetime) -> list[ObservationInput]: ...

    async def count_for_contributor(self, contributor_id: int, since: datetime) -> int: ...


class ContributorRepository(Protocol):
    async def get_or_create(self, device_hash: str) -> ContributorRef: ...

    async def set_reputation(self, contributor_id: int, reputation: float) -> None: ...


class StatusRepository(Protocol):
    async def upsert_spot(self, spot_id: int, status: DerivedStatus) -> None: ...

    async def upsert_field(self, field_id: int, status: DerivedFieldStatus) -> None: ...


class StatusPublisher(Protocol):
    async def publish(self, spot: SpotRef, status: DerivedStatus) -> None: ...


class FeedRepository(Protocol):
    async def get(self, feed_id: str) -> FeedRef: ...

    async def token_hash(self, feed_id: str) -> str: ...

    async def touch(self, feed_id: str, *, accepted: int, rejected: int, at: datetime) -> None: ...

    async def resolve_spot(self, feed: FeedRef, external_id: str) -> SpotRef: ...

    async def resolve_field(self, feed: FeedRef, external_id: str) -> FieldRef: ...

    async def health(self, feed_id: str, now: datetime) -> dict[str, Any]: ...
