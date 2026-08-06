"""OSM tag mapping (docs/03 §B). ODbL-derived rows keep `source_id = 'osm'` forever (docs/04 §2)."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from balise_api.domain.enums import SpotKind

from balise_ingest.records import (
    FieldRecord,
    HarbourRecord,
    NavAidRecord,
    NormalisedBatch,
    RawFeature,
    SourceRecord,
    SpotRecord,
)
from balise_ingest.slugs import slugify
from balise_ingest.sources import osm as osm_source

_MOORING_KIND: dict[str, SpotKind] = {
    "buoy": SpotKind.MOORING_BUOY,
    "pile": SpotKind.PILE,
    "bollard": SpotKind.QUAY,
    "dolphin": SpotKind.QUAY,
    "wall": SpotKind.QUAY,
    "chain": SpotKind.MOORING_BUOY,
    "post": SpotKind.PILE,
}

_SEAMARK_NAV_AID_CLASS: dict[str, str] = {
    "buoy_lateral": "boylat",
    "buoy_cardinal": "boycar",
    "buoy_isolated_danger": "boyisd",
    "buoy_safe_water": "boysaw",
    "buoy_special_purpose": "boyspp",
    "buoy_installation": "boyinb",
    "beacon_lateral": "bcnlat",
    "beacon_cardinal": "bcncar",
    "beacon_isolated_danger": "bcnisd",
    "beacon_safe_water": "bcnsaw",
    "beacon_special_purpose": "bcnspp",
    "landmark": "lndmrk",
}

_CARDINAL_FR = {"north": "nord", "east": "est", "south": "sud", "west": "ouest"}
_LATERAL_FR = {
    "port": "bâbord",
    "starboard": "tribord",
    "preferred_channel_port": "chenal préféré à bâbord",
    "preferred_channel_starboard": "chenal préféré à tribord",
}
_SERVICE_TAGS = {
    "drinking_water": "water",
    "fuel": "fuel",
    "shower": "showers",
    "toilets": "toilets",
    "waste_disposal": "waste",
    "sanitary_dump_station": "pump_out",
    "internet_access": "wifi",
    "electricity": "electricity",
    "crane": "boat_lift",
}

logger = logging.getLogger(__name__)


def _point(feature: RawFeature) -> tuple[float, float] | None:
    geometry = feature.geometry
    if geometry is None:
        return None
    coordinates: Any = geometry["coordinates"]
    while isinstance(coordinates, list) and coordinates and isinstance(coordinates[0], list):
        coordinates = coordinates[0]
    if not coordinates:
        return None
    return float(coordinates[0]), float(coordinates[1])


def _decimal(tags: dict[str, str], key: str) -> Decimal | None:
    raw = tags.get(key)
    if not raw:
        return None
    try:
        return Decimal(raw.split(";")[0].strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _integer(tags: dict[str, str], key: str) -> int | None:
    raw = tags.get(key)
    if not raw or not raw.strip().isdigit():
        return None
    return int(raw.strip())


def _vhf(tags: dict[str, str]) -> int | None:
    raw = tags.get("vhf_channel") or tags.get("seamark:radio_station:channel")
    if not raw:
        return None
    digits = "".join(character for character in raw if character.isdigit())
    return int(digits) if digits else None


def _services(tags: dict[str, str]) -> tuple[str, ...]:
    found = {
        service
        for tag, service in _SERVICE_TAGS.items()
        if tags.get(tag) in {"yes", "customers", "public"} or tags.get(f"service:{tag}") == "yes"
    }
    if tags.get("seamark:small_craft_facility:category"):
        found.add("visitor_berth")
    return tuple(sorted(found))


def _harbour(feature: RawFeature) -> HarbourRecord | None:
    tags = feature.properties
    point = _point(feature)
    name = tags.get("name")
    if point is None or not name:
        return None
    return HarbourRecord(
        external_id=feature.external_id,
        source_id="osm",
        slug=slugify(name),
        name=name,
        lon=point[0],
        lat=point[1],
        vhf_channel=_vhf(tags),
        phone=tags.get("phone") or tags.get("contact:phone"),
        email=tags.get("email") or tags.get("contact:email"),
        website=tags.get("website") or tags.get("contact:website"),
        opening_hours=tags.get("opening_hours"),
        services=_services(tags),
        attrs_provenance=dict.fromkeys(("position", "name", "phone", "website", "services"), "osm"),
    )


def _mooring_spot(feature: RawFeature) -> SpotRecord | None:
    tags = feature.properties
    point = _point(feature)
    if point is None:
        return None
    category = tags.get("seamark:mooring:category", "buoy")
    kind = _MOORING_KIND.get(category, SpotKind.MOORING_BUOY)
    return SpotRecord(
        external_id=feature.external_id,
        source_id="osm",
        kind=kind,
        lon=point[0],
        lat=point[1],
        code=tags.get("seamark:mooring:name") or tags.get("ref") or tags.get("name"),
        depth_m=_decimal(tags, "seamark:mooring:depth") or _decimal(tags, "depth"),
        max_loa_m=_decimal(tags, "maxlength") or _decimal(tags, "seamark:mooring:maximum_length"),
        max_draft_m=_decimal(tags, "maxdraft") or _decimal(tags, "seamark:mooring:maximum_draught"),
        max_beam_m=_decimal(tags, "maxwidth"),
        visitor=tags.get("seamark:mooring:category") == "buoy" and tags.get("access") != "private",
        bookable=tags.get("fee") in {"yes", "customers"},
        attrs_provenance=dict.fromkeys(
            ("position", "kind", "depth_m", "max_loa_m", "max_draft_m"), "osm"
        ),
    )


def _anchorage_spot(feature: RawFeature) -> SpotRecord | None:
    point = _point(feature)
    if point is None:
        return None
    tags = feature.properties
    return SpotRecord(
        external_id=feature.external_id,
        source_id="osm",
        kind=SpotKind.ANCHORAGE,
        lon=point[0],
        lat=point[1],
        code=tags.get("name"),
        depth_m=_decimal(tags, "seamark:anchorage:depth") or _decimal(tags, "depth"),
        holding=tags.get("seabed:surface") or tags.get("seamark:anchorage:seabed"),
        attrs_provenance={"position": "osm", "kind": "osm"},
    )


def _pontoon_field(feature: RawFeature) -> FieldRecord | None:
    tags = feature.properties
    return FieldRecord(
        external_id=feature.external_id,
        source_id="osm",
        kind=SpotKind.BERTH,
        name=tags.get("name") or tags.get("ref"),
        capacity=_integer(tags, "capacity"),
        visitor_capacity=_integer(tags, "capacity:visitor"),
        operator=tags.get("operator"),
    )


def _nav_aid(feature: RawFeature, s57_class: str) -> NavAidRecord | None:
    point = _point(feature)
    if point is None:
        return None
    tags = feature.properties
    seamark = tags.get("seamark:type", "")
    category = tags.get(f"seamark:{seamark}:category")
    label = _CARDINAL_FR.get(category or "") or _LATERAL_FR.get(category or "") or category
    light = None
    if tags.get("seamark:light:character"):
        light = {
            "osm_character": tags.get("seamark:light:character"),
            "osm_colour": tags.get("seamark:light:colour"),
            "osm_period": tags.get("seamark:light:period"),
            "osm_range": tags.get("seamark:light:range"),
        }
    return NavAidRecord(
        external_id=feature.external_id,
        source_id="osm",
        s57_class=s57_class,
        lon=point[0],
        lat=point[1],
        name=tags.get("seamark:name") or tags.get("name"),
        colour=tags.get(f"seamark:{seamark}:colour"),
        colour_pattern=tags.get(f"seamark:{seamark}:colour_pattern"),
        shape=tags.get(f"seamark:{seamark}:shape"),
        topmark=tags.get("seamark:topmark:shape"),
        category=label,
        light=light,
        raw=dict(tags),
    )


def normalise(features: list[RawFeature], source: SourceRecord | None = None) -> NormalisedBatch:
    source = source or osm_source.SOURCE
    harbours: list[HarbourRecord] = []
    spots: list[SpotRecord] = []
    fields: list[FieldRecord] = []
    nav_aids: list[NavAidRecord] = []

    for feature in features:
        tags = feature.properties
        seamark = tags.get("seamark:type")
        if tags.get("leisure") == "marina" or tags.get("seamark:harbour:category") == "marina":
            harbour = _harbour(feature)
            if harbour is not None:
                harbours.append(harbour)
            continue
        if seamark == "mooring":
            spot = _mooring_spot(feature)
            if spot is not None:
                spots.append(spot)
        elif seamark == "anchorage":
            anchorage = _anchorage_spot(feature)
            if anchorage is not None:
                spots.append(anchorage)
        elif seamark == "berth" or tags.get("man_made") == "pier":
            field = _pontoon_field(feature)
            if field is not None:
                fields.append(field)
        elif seamark in _SEAMARK_NAV_AID_CLASS:
            nav_aid = _nav_aid(feature, _SEAMARK_NAV_AID_CLASS[seamark])
            if nav_aid is not None:
                nav_aids.append(nav_aid)

    batch = NormalisedBatch(
        source=source,
        nav_aids=tuple(nav_aids),
        harbours=tuple(harbours),
        fields=tuple(fields),
        spots=tuple(spots),
    )
    logger.info("osm normalised: %s", batch.counts())
    return batch
