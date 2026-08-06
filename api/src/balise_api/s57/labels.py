"""Compose the sailor-facing French description of a navigation mark (docs/08 `/navaids/{id}`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from balise_api.s57.codes import (
    CLASS_LABELS,
    LIGHT_ABBREVIATIONS,
    UnknownS57Code,
    decode,
    decode_many,
)

_CATEGORY_ATTRIBUTE: dict[str, str] = {
    "bcnlat": "catlam",
    "boylat": "catlam",
    "bcncar": "catcam",
    "boycar": "catcam",
    "bcnspp": "catspm",
    "boyspp": "catspm",
    "lndmrk": "catlmk",
    "morfac": "catmor",
    "achare": "catach",
    "hrbfac": "cathaf",
}

_SHAPE_ATTRIBUTE: dict[str, str] = {
    "boylat": "boyshp",
    "boycar": "boyshp",
    "boyisd": "boyshp",
    "boysaw": "boyshp",
    "boyspp": "boyshp",
    "boyinb": "boyshp",
    "bcnlat": "bcnshp",
    "bcncar": "bcnshp",
    "bcnisd": "bcnshp",
    "bcnsaw": "bcnshp",
    "bcnspp": "bcnshp",
}


def category_attribute(s57_class: str) -> str | None:
    return _CATEGORY_ATTRIBUTE.get(s57_class)


def shape_attribute(s57_class: str) -> str | None:
    return _SHAPE_ATTRIBUTE.get(s57_class)


def navaid_label(s57_class: str, category: str | None) -> str:
    """`("boylat", "bâbord")` → `"Bouée latérale bâbord"`."""
    base = CLASS_LABELS.get(s57_class)
    if base is None:
        raise UnknownS57Code("s57_class", s57_class)
    if not category:
        return base
    return f"{base} {category}"


@dataclass(frozen=True, slots=True)
class LightDescription:
    text: str
    character: str | None
    period_s: float | None
    colour: str | None
    range_nm: float | None
    group: str | None
    sectors: bool


def _numeric(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def describe_light(raw: dict[str, Any] | None) -> LightDescription | None:
    """Build `Fl R 4s 7M` and its French reading from an S-57 `lights` feature's properties."""
    if not raw:
        return None
    litchr_raw = raw.get("litchr")
    character = decode("litchr", litchr_raw)
    colours = decode_many("colour", raw.get("colour"))
    period = _numeric(raw.get("sigper"))
    value_range = _numeric(raw.get("valnmr"))
    group = str(raw["siggrp"]).strip("()") if raw.get("siggrp") else None

    abbreviation = LIGHT_ABBREVIATIONS.get(int(litchr_raw)) if litchr_raw else None
    parts: list[str] = []
    if abbreviation:
        parts.append(f"{abbreviation}({group})" if group else abbreviation)
    parts.extend(colour[0].upper() for colour in colours if colour)
    if period is not None:
        parts.append(f"{period:g}s")
    if value_range is not None:
        parts.append(f"{value_range:g}M")
    return LightDescription(
        text=" ".join(parts),
        character=character,
        period_s=period,
        colour=", ".join(colours) or None,
        range_nm=value_range,
        group=group,
        sectors=raw.get("sectr1") is not None,
    )
