"""SHOM raw features → normalised records (docs/03 §A, docs/10).

Never lossy: the whole `properties` object goes into `nav_aid.raw`. Unknown codes raise.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import replace
from decimal import Decimal
from typing import Any

from balise_api.domain.enums import SpotKind

from balise_ingest.records import (
    FieldRecord,
    HarbourRecord,
    NavAidRecord,
    NormalisedBatch,
    RawFeature,
    ServicePoint,
    SourceRecord,
    SpmPort,
    SpotRecord,
)
from balise_ingest.s57_codes import (
    SMCFAC_SERVICES,
    decode_many,
    decode_strict,
    validate_layer,
)
from balise_ingest.slugs import slugify

NAV_AID_LAYERS = (
    "bcnlat",
    "bcncar",
    "bcnisd",
    "bcnspp",
    "boylat",
    "boycar",
    "boyisd",
    "boysaw",
    "boyspp",
    "boyinb",
    "lndmrk",
)
_CATEGORY_ATTRIBUTE = {
    "bcnlat": "catlam",
    "boylat": "catlam",
    "bcncar": "catcam",
    "boycar": "catcam",
    "bcnspp": "catspm",
    "boyspp": "catspm",
    "lndmrk": "catlmk",
}
_SHAPE_ATTRIBUTE = {"boy": "boyshp", "bcn": "bcnshp"}

#: S-57 CATMOR → our spot kinds. Dolphins and chains (1, 2, 6) are not places to stop.
_MORFAC_KIND: dict[int, SpotKind] = {
    3: SpotKind.QUAY,
    4: SpotKind.QUAY,
    5: SpotKind.PILE,
    7: SpotKind.MOORING_BUOY,
}
#: CATHAF values we treat as a plaisance harbour (docs/00 excludes commercial ports).
_MARINA_CATHAF = {5, 14}

logger = logging.getLogger(__name__)


def _point(feature: RawFeature) -> tuple[float, float] | None:
    geometry = feature.geometry
    if geometry is None:
        return None
    if geometry["type"] == "Point":
        lon, lat = geometry["coordinates"][:2]
        return float(lon), float(lat)
    coordinates: Any = geometry["coordinates"]
    while isinstance(coordinates, list) and coordinates and isinstance(coordinates[0], list):
        coordinates = coordinates[0]
    return (float(coordinates[0]), float(coordinates[1])) if coordinates else None


def _name(properties: dict[str, Any]) -> str | None:
    value = properties.get("nobjnm") or properties.get("objnam")
    return str(value) if value not in (None, "") else None


def _decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value not in (None, "") else None


def _nav_aid(
    feature: RawFeature, lights: dict[str, dict[str, Any]], topmarks: dict[str, str]
) -> NavAidRecord | None:
    point = _point(feature)
    if point is None:
        return None
    properties = feature.properties
    validate_layer(feature.layer, properties)
    category_attribute = _CATEGORY_ATTRIBUTE.get(feature.layer)
    shape_attribute = _SHAPE_ATTRIBUTE.get(feature.layer[:3])
    light_ids = str(properties.get("lights") or "").split(",")
    light = next((lights[key] for key in light_ids if key in lights), None)
    return NavAidRecord(
        external_id=feature.external_id,
        source_id="shom.balisage",
        s57_class=feature.layer,
        lon=point[0],
        lat=point[1],
        inspire_id=str(properties["inspireid"]) if properties.get("inspireid") else None,
        name=_name(properties),
        colour=", ".join(decode_many("colour", properties.get("colour"))) or None,
        colour_pattern=", ".join(decode_many("colpat", properties.get("colpat"))) or None,
        shape=decode_strict(feature.layer, shape_attribute, properties.get(shape_attribute))
        if shape_attribute
        else None,
        topmark=topmarks.get(str(properties.get("topmar") or "")),
        category=decode_strict(
            feature.layer, category_attribute, properties.get(category_attribute)
        )
        if category_attribute
        else None,
        light=light,
        height_m=_decimal(properties.get("height")),
        raw=properties,
    )


def _morfac_spot(feature: RawFeature) -> SpotRecord | None:
    point = _point(feature)
    if point is None:
        return None
    validate_layer(feature.layer, feature.properties)
    raw_category = feature.properties.get("catmor")
    if raw_category in (None, ""):
        return None
    kind = _MORFAC_KIND.get(int(raw_category))
    if kind is None:
        return None
    return SpotRecord(
        external_id=feature.external_id,
        source_id="shom.balisage",
        kind=kind,
        lon=point[0],
        lat=point[1],
        code=_name(feature.properties),
        attrs_provenance={"position": "shom.balisage", "kind": "shom.balisage"},
    )


def _anchorage_field(feature: RawFeature) -> FieldRecord | None:
    validate_layer(feature.layer, feature.properties)
    if feature.geometry is None:
        return None
    properties = feature.properties
    restrictions = decode_many("restrn", properties.get("restrn"))
    if "mouillage interdit" in restrictions:
        return None
    return FieldRecord(
        external_id=feature.external_id,
        source_id="shom.reglementation",
        kind=SpotKind.ANCHORAGE,
        name=_name(properties) or decode_strict(feature.layer, "catach", properties.get("catach")),
        price_note=str(properties.get("ninfom")) if properties.get("ninfom") else None,
        area_geojson=feature.geometry,
    )


def _anchorage_spot(feature: RawFeature) -> SpotRecord | None:
    point = _point(feature)
    if point is None:
        return None
    validate_layer(feature.layer, feature.properties)
    properties = feature.properties
    if "mouillage interdit" in decode_many("restrn", properties.get("restrn")):
        return None
    return SpotRecord(
        external_id=feature.external_id,
        source_id="shom.reglementation",
        kind=SpotKind.ANCHORAGE,
        lon=point[0],
        lat=point[1],
        code=_name(properties),
        attrs_provenance={"position": "shom.reglementation", "kind": "shom.reglementation"},
    )


def _harbour(feature: RawFeature) -> HarbourRecord | None:
    point = _point(feature)
    name = _name(feature.properties)
    validate_layer(feature.layer, feature.properties)
    category = feature.properties.get("cathaf")
    if point is None or name is None or category in (None, ""):
        return None
    if int(category) not in _MARINA_CATHAF:
        return None
    return HarbourRecord(
        external_id=feature.external_id,
        source_id="shom.ports",
        slug=slugify(name),
        name=name,
        lon=point[0],
        lat=point[1],
        attrs_provenance={"position": "shom.ports", "name": "shom.ports"},
    )


def _berth(feature: RawFeature) -> SpotRecord | None:
    point = _point(feature)
    if point is None:
        return None
    return SpotRecord(
        external_id=feature.external_id,
        source_id="shom.ports",
        kind=SpotKind.BERTH,
        lon=point[0],
        lat=point[1],
        code=_name(feature.properties),
        attrs_provenance={"position": "shom.ports", "kind": "shom.ports"},
    )


def _service_point(feature: RawFeature) -> ServicePoint | None:
    point = _point(feature)
    raw_category = feature.properties.get("catscf")
    if point is None or raw_category in (None, ""):
        return None
    service = SMCFAC_SERVICES.get(int(raw_category))
    if service is None:
        return None
    return ServicePoint(
        external_id=feature.external_id, service=service, lon=point[0], lat=point[1]
    )


def _spm_port(feature: RawFeature) -> SpmPort | None:
    properties = feature.properties
    point = _point(feature)
    if point is None or not properties.get("cst"):
        return None
    return SpmPort(
        key=str(properties["cst"]),
        name=str(properties.get("toponyme") or properties["cst"]),
        lon=point[0],
        lat=point[1],
        reference=str(properties["ch_ref"]) if properties.get("ch_ref") else None,
    )


def normalise(
    group: str, layers: dict[str, list[RawFeature]], source: SourceRecord
) -> NormalisedBatch:
    lights = {feature.external_id: feature.properties for feature in layers.get("lights", [])}
    topmarks: dict[str, str] = {}
    for feature in layers.get("topmar", []):
        label = decode_strict("topmar", "topshp", feature.properties.get("topshp"))
        if label:
            topmarks[feature.external_id] = label

    nav_aids: list[NavAidRecord] = []
    spots: list[SpotRecord] = []
    fields: list[FieldRecord] = []
    harbours: list[HarbourRecord] = []
    services: list[ServicePoint] = []
    spm_ports: list[SpmPort] = []

    for layer, features in layers.items():
        for feature in features:
            if layer in NAV_AID_LAYERS:
                record = _nav_aid(feature, lights, topmarks)
                if record is not None:
                    nav_aids.append(record)
            elif layer == "morfac":
                spot = _morfac_spot(feature)
                if spot is not None:
                    spots.append(spot)
            elif layer == "achare_polygon":
                anchorage = _anchorage_field(feature)
                if anchorage is not None:
                    fields.append(anchorage)
            elif layer == "achare_point":
                anchor_spot = _anchorage_spot(feature)
                if anchor_spot is not None:
                    spots.append(anchor_spot)
            elif layer in {"hrbfac_point", "hrbfac_polygon"}:
                harbour = _harbour(feature)
                if harbour is not None:
                    harbours.append(harbour)
            elif layer == "berths_point":
                berth = _berth(feature)
                if berth is not None:
                    spots.append(berth)
            elif layer == "smcfac_point":
                service = _service_point(feature)
                if service is not None:
                    services.append(service)
            elif layer == "liste_ports_spm_h2m":
                spm = _spm_port(feature)
                if spm is not None:
                    spm_ports.append(spm)

    batch = NormalisedBatch(
        source=source,
        nav_aids=tuple(nav_aids),
        harbours=tuple(_dedupe_slugs(harbours)),
        fields=tuple(fields),
        spots=tuple(spots),
        service_points=tuple(services),
        spm_ports=tuple(spm_ports),
    )
    logger.info("shom %s normalised: %s", group, batch.counts())
    return batch


def _dedupe_slugs(harbours: list[HarbourRecord]) -> list[HarbourRecord]:
    seen: Counter[str] = Counter()
    out: list[HarbourRecord] = []
    for harbour in harbours:
        seen[harbour.slug] += 1
        count = seen[harbour.slug]
        out.append(harbour if count == 1 else replace(harbour, slug=f"{harbour.slug}-{count}"))
    return out
