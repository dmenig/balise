from __future__ import annotations

from balise_api.schemas.common import Model
from balise_api.schemas.spots import FieldSummary


class HarbourListItem(Model):
    id: str
    slug: str
    name: str
    position: list[float]
    insee_code: str | None = None
    distance_nm: float | None = None
    spot_count: int = 0


class HarbourList(Model):
    harbours: list[HarbourListItem]
    attribution: list[str]


class HarbourDetail(Model):
    id: str
    slug: str
    name: str
    position: list[float]
    insee_code: str | None = None
    vhf_channel: int | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    opening_hours: str | None = None
    services: list[str]
    fields: list[FieldSummary]
    spot_count: int
    attribution: list[str]
    disclaimer: str
