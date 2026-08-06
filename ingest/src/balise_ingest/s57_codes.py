"""Ingest-side S-57 decoding.

The code tables themselves live in `balise_api.s57` (the API needs them to render
`/navaids/{id}`); this module adds the ingest contract: **an unknown code fails the job**
(docs/10) instead of silently producing an unlabelled mark.
"""

from __future__ import annotations

from typing import Any

from balise_api.s57 import CLASS_LABELS, CODE_LISTS, UnknownS57Code, decode, decode_many

__all__ = [
    "CLASS_LABELS",
    "CODE_LISTS",
    "LIST_ATTRIBUTES",
    "SMCFAC_SERVICES",
    "UnknownS57Code",
    "decode",
    "decode_labels",
    "decode_many",
    "decode_strict",
    "numeric_codes",
    "validate_layer",
]

#: S-57 Appendix A types every one of these as a *list*: SHOM packs the codes as `"16,50"`.
#: Decoding one of them as a scalar raises on the second value, which is a real mark, not a
#: data error — `bcnspp.catspm` alone does it a few dozen times outside the Morbihan bbox.
LIST_ATTRIBUTES = frozenset({"catach", "catlmk", "catspm", "cathaf", "colour", "colpat", "restrn"})

#: Attributes we interpret per layer. Anything else lands untouched in `nav_aid.raw`.
DECODED_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "bcnlat": ("catlam", "colour", "colpat", "bcnshp"),
    "bcncar": ("catcam", "colour", "colpat", "bcnshp"),
    "bcnisd": ("colour", "colpat", "bcnshp"),
    "bcnsaw": ("colour", "colpat", "bcnshp"),
    "bcnspp": ("catspm", "colour", "colpat", "bcnshp"),
    "boylat": ("catlam", "colour", "colpat", "boyshp"),
    "boycar": ("catcam", "colour", "colpat", "boyshp"),
    "boyisd": ("colour", "colpat", "boyshp"),
    "boysaw": ("colour", "colpat", "boyshp"),
    "boyspp": ("catspm", "colour", "colpat", "boyshp"),
    "boyinb": ("colour", "colpat", "boyshp"),
    "lndmrk": ("catlmk", "colour", "convis"),
    "morfac": ("catmor", "colour", "colpat"),
    "lights": ("litchr", "colour"),
    "topmar": ("topshp", "colour"),
    "achare_point": ("catach", "restrn"),
    "achare_polygon": ("catach", "restrn"),
    "hrbfac_point": ("cathaf",),
    "hrbfac_polygon": ("cathaf",),
}

#: S-57 CATSCF → our `harbour.services` vocabulary (docs/05).
SMCFAC_SERVICES: dict[int, str] = {
    1: "visitor_berth",
    2: "nautical_club",
    3: "boat_hoist",
    5: "boatyard",
    7: "restaurant",
    8: "chandler",
    9: "provisions",
    12: "water",
    13: "fuel",
    14: "electricity",
    16: "showers",
    17: "laundry",
    19: "waste",
    20: "parking",
    24: "pump_out",
    27: "harbour_office",
    28: "pump_out",
    29: "slipway",
    30: "visitor_mooring",
    31: "careening",
    33: "mechanic",
    36: "boat_lift",
}


def decode_strict(layer: str, attribute: str, value: Any) -> str | None:
    """Decode, raising `UnknownS57Code` with the layer in the message for a readable failure."""
    try:
        return decode(attribute, value)
    except UnknownS57Code as exc:
        raise UnknownS57Code(f"{layer}.{attribute}", exc.code) from exc


def decode_labels(layer: str, attribute: str, value: Any) -> list[str]:
    """Every label of one attribute, list-typed or not, with the layer named in any failure."""
    try:
        if attribute in LIST_ATTRIBUTES:
            return decode_many(attribute, value)
        label = decode(attribute, value)
        return [] if label is None else [label]
    except UnknownS57Code as exc:
        raise UnknownS57Code(f"{layer}.{attribute}", exc.code) from exc


def numeric_codes(value: Any) -> set[int]:
    """The raw codes of a list attribute, for the cases that switch on the number, not the label."""
    if value is None or value == "":
        return set()
    return {int(part) for part in str(value).replace(";", ",").split(",") if part.strip()}


def validate_layer(layer: str, properties: dict[str, Any]) -> None:
    """Assert every code we interpret in this layer decodes. Runs on every ingested feature."""
    for attribute in DECODED_ATTRIBUTES.get(layer, ()):
        decode_labels(layer, attribute, properties.get(attribute))
