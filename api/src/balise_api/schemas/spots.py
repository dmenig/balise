from __future__ import annotations

from datetime import datetime

from balise_api.domain.enums import SourceKind, SpotKind, SpotState
from balise_api.schemas.common import FieldStatusOut, Model, StatusOut


class SpotProperties(Model):
    kind: SpotKind
    code: str | None = None
    harbour_id: str | None = None
    harbour_name: str | None = None
    field_id: str | None = None
    visitor: bool = False
    depth_m: float | None = None
    max_loa_m: float | None = None
    max_draft_m: float | None = None
    max_beam_m: float | None = None
    holding: str | None = None
    exposure: list[str] = []  # noqa: RUF012 - pydantic copies defaults per instance
    price_per_night_cents: int | None = None
    #: 🔌 `null` in v1 and for any spot nobody has reported in v2 (docs/06 §A/S3, docs/08).
    #: Clients must treat null as "unknown", never as an error — that is the whole contract.
    status: StatusOut | None = None


class ObservationTrace(Model):
    """Source kind and age only — never the contributor (docs/04 §4)."""

    source_kind: SourceKind
    state: SpotState
    age_seconds: int
    confidence: float


class TideExtreme(Model):
    at: datetime
    height_m: float
    kind: str
    coefficient: int | None = None


class TideSummary(Model):
    harbour_id: str
    next_high_water: TideExtreme | None = None
    next_low_water: TideExtreme | None = None
    depth_at_next_low_water_m: float | None = None
    is_estimate: bool = True
    note: str
    attribution: list[str]


class WeatherPoint(Model):
    at: datetime
    wind_kt: float | None = None
    gust_kt: float | None = None
    wind_dir_deg: int | None = None
    wave_m: float | None = None


class WeatherSummary(Model):
    harbour_id: str
    points: list[WeatherPoint]
    is_estimate: bool = True
    attribution: list[str]


class FieldSummary(Model):
    id: str
    name: str | None = None
    kind: SpotKind
    capacity: int | None = None
    visitor_capacity: int | None = None
    operator: str | None = None
    price_per_night_cents: int | None = None
    price_note: str | None = None
    status: FieldStatusOut | None = None


class HarbourSummary(Model):
    id: str
    slug: str
    name: str
    vhf_channel: int | None = None
    phone: str | None = None
    website: str | None = None
    opening_hours: str | None = None
    services: list[str] = []  # noqa: RUF012


class SpotDetail(Model):
    id: str
    kind: SpotKind
    code: str | None
    position: list[float]
    properties: SpotProperties
    field: FieldSummary | None = None
    harbour: HarbourSummary | None = None
    #: 🔌 v2 adds the last 5 observations (source kind and age only, never who).
    observations: list[ObservationTrace] = []  # noqa: RUF012
    tide: TideSummary | None = None
    weather: WeatherSummary | None = None
    warnings: list[str]
    attribution: list[str]
    disclaimer: str


class StatusMapEntry(Model):
    free: int | None = None
    capacity: int | None = None
    confidence: float


class StatusMap(Model):
    """The volatile companion to cached tiles (docs/08 `GET /status`)."""

    as_of: datetime
    spots: dict[str, tuple[SpotState, float, datetime, SourceKind]]
    fields: dict[str, StatusMapEntry]
