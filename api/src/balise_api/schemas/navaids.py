from __future__ import annotations

from balise_api.schemas.common import Model


class LightOut(Model):
    text: str
    character: str | None = None
    period_s: float | None = None
    colour: str | None = None
    range_nm: float | None = None
    group: str | None = None
    sectors: bool = False


class NavAidDetail(Model):
    """S-57 codes are translated to plain French here and nowhere else (docs/08)."""

    id: str
    s57_class: str
    label: str
    name: str | None = None
    colour: str | None = None
    colour_pattern: str | None = None
    shape: str | None = None
    topmark: str | None = None
    category: str | None = None
    height_m: float | None = None
    light: LightOut | None = None
    position: list[float]
    explainer: str
    source: str
    disclaimer: str
