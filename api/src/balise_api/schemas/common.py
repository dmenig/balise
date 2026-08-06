from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from balise_api.domain.enums import ConfidenceBucket, SourceKind, SpotState
from balise_api.domain.observation import DerivedStatus


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)


class ProblemDetail(Model):
    """RFC 9457."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class StatusOut(Model):
    """What we are willing to *show*: display state, confidence, source and age.

    Never a naked green dot (docs/06).
    """

    state: SpotState
    confidence: float
    bucket: ConfidenceBucket
    #: Absent when the state is `unknown`: there is no instant to date something we do not know,
    #: and embedding "now" would change the payload on every request and defeat its ETag.
    as_of: datetime | None = None
    source_kind: SourceKind | None = None
    age_seconds: int | None = None

    @classmethod
    def from_derived(cls, status: DerivedStatus, now: datetime) -> StatusOut:
        if status.display_state is SpotState.UNKNOWN:
            return cls.unknown(now)
        as_of = status.as_of if status.as_of.tzinfo else status.as_of.replace(tzinfo=UTC)
        return cls(
            state=status.display_state,
            confidence=status.confidence,
            bucket=status.bucket,
            as_of=as_of,
            source_kind=status.source_kind,
            age_seconds=max(int((now - as_of).total_seconds()), 0),
        )

    @classmethod
    def unknown(cls, now: datetime) -> StatusOut:
        return cls(state=SpotState.UNKNOWN, confidence=0.0, bucket=ConfidenceBucket.UNKNOWN)


class FieldStatusOut(Model):
    free: int | None
    capacity: int | None
    confidence: float
    as_of: datetime | None = None
    source_kind: SourceKind | None = None


class Geometry(Model):
    type: Literal["Point", "Polygon", "MultiPolygon"]
    coordinates: Any


class Feature(Model):
    type: Literal["Feature"] = "Feature"
    id: str
    geometry: Geometry
    properties: dict[str, Any]


class FeatureCollection(Model):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature]
    attribution: list[str]
    next_cursor: str | None = None
    disclaimer: str


Bbox = Annotated[str, Field(pattern=r"^-?\d+(\.\d+)?(,-?\d+(\.\d+)?){3}$")]


class BboxValue(Model):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    @classmethod
    def parse(cls, raw: str, max_span_deg: float = 2.0) -> BboxValue:
        parts = [float(value) for value in raw.split(",")]
        box = cls(min_lon=parts[0], min_lat=parts[1], max_lon=parts[2], max_lat=parts[3])
        if box.min_lon >= box.max_lon or box.min_lat >= box.max_lat:
            raise ValueError("bbox inversée")
        if box.max_lon - box.min_lon > max_span_deg or box.max_lat - box.min_lat > max_span_deg:
            raise ValueError(f"bbox trop large (max {max_span_deg}°)")
        return box
