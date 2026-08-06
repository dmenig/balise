"""Normalised records — the only shape that reaches conflation and loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from balise_api.domain.enums import SpotKind


@dataclass(frozen=True, slots=True)
class RawFeature:
    """One feature as fetched, before any interpretation. Snapshots store exactly this."""

    external_id: str
    layer: str
    geometry: dict[str, Any] | None
    properties: dict[str, Any]


@dataclass(frozen=True, slots=True)
class NavAidRecord:
    external_id: str
    source_id: str
    s57_class: str
    lon: float
    lat: float
    inspire_id: str | None = None
    name: str | None = None
    colour: str | None = None
    colour_pattern: str | None = None
    shape: str | None = None
    topmark: str | None = None
    category: str | None = None
    light: dict[str, Any] | None = None
    height_m: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HarbourRecord:
    external_id: str
    source_id: str
    slug: str
    name: str
    lon: float
    lat: float
    insee_code: str | None = None
    vhf_channel: int | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    opening_hours: str | None = None
    services: tuple[str, ...] = ()
    attrs_provenance: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FieldRecord:
    external_id: str
    source_id: str
    kind: SpotKind
    name: str | None = None
    harbour_external_id: str | None = None
    capacity: int | None = None
    visitor_capacity: int | None = None
    operator: str | None = None
    price_per_night_cents: int | None = None
    price_note: str | None = None
    area_geojson: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class SpotRecord:
    external_id: str
    source_id: str
    kind: SpotKind
    lon: float
    lat: float
    code: str | None = None
    field_external_id: str | None = None
    harbour_external_id: str | None = None
    depth_m: Decimal | None = None
    max_loa_m: Decimal | None = None
    max_beam_m: Decimal | None = None
    max_draft_m: Decimal | None = None
    holding: str | None = None
    exposure: tuple[str, ...] = ()
    visitor: bool = False
    bookable: bool = False
    area_geojson: dict[str, Any] | None = None
    attrs_provenance: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ServicePoint:
    """A SHOM `smcfac` facility, attached to the nearest harbour during conflation."""

    external_id: str
    service: str
    lon: float
    lat: float


@dataclass(frozen=True, slots=True)
class SpmPort:
    """A SHOM tide reference port — the join key for the tide API (docs/03 §D)."""

    key: str
    name: str
    lon: float
    lat: float
    reference: str | None = None


@dataclass(frozen=True, slots=True)
class SourceRecord:
    id: str
    kind: str
    licence: str
    attribution: str
    url: str | None = None


@dataclass(frozen=True, slots=True)
class NormalisedBatch:
    source: SourceRecord
    nav_aids: tuple[NavAidRecord, ...] = ()
    harbours: tuple[HarbourRecord, ...] = ()
    fields: tuple[FieldRecord, ...] = ()
    spots: tuple[SpotRecord, ...] = ()
    service_points: tuple[ServicePoint, ...] = ()
    spm_ports: tuple[SpmPort, ...] = ()

    def counts(self) -> dict[str, int]:
        return {
            "nav_aids": len(self.nav_aids),
            "harbours": len(self.harbours),
            "fields": len(self.fields),
            "spots": len(self.spots),
            "service_points": len(self.service_points),
            "spm_ports": len(self.spm_ports),
        }
