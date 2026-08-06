"""Regenerate a checked-in extract from the live sources.

    uv run python -m balise_ingest.make_fixture --bbox -3.2,47.4,-2.6,47.8
    uv run python -m balise_ingest.make_fixture --name bretagne --bbox -5.4,47.15,-1.0,49.0 \
        --no-caps --out ingest/src/balise_ingest/fixtures/bretagne.geojson

Run this deliberately, review the diff, commit it. `make seed` then needs no network at all.
The capped default is the seed fixture (small enough to stay reviewable in git); `--no-caps`
produces the full regional extract the web app reads.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from balise_ingest.normalisers import osm as osm_normaliser
from balise_ingest.normalisers import shom as shom_normaliser
from balise_ingest.records import (
    FieldRecord,
    HarbourRecord,
    NavAidRecord,
    NormalisedBatch,
    SpotRecord,
)
from balise_ingest.seed import FIXTURE
from balise_ingest.sources import osm, shom

DEFAULT_BBOX = "-3.2,47.4,-2.6,47.8"
logger = logging.getLogger("make_fixture")


@dataclass(frozen=True, slots=True)
class Caps:
    """Enough to exercise every layer and both licences, small enough to stay reviewable in git."""

    nav_aids: int | None = 250
    spots: int | None = 250
    fields: int | None = 100
    harbours: int | None = 60


UNCAPPED = Caps(None, None, None, None)


def _point(lon: float, lat: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [round(lon, 7), round(lat, 7)]}


def _clean(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value not in (None, "", [], {}, ())}


def _feature(geometry: dict[str, Any] | None, properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "geometry": geometry, "properties": _clean(properties)}


def _compact(raw: dict[str, Any]) -> dict[str, Any]:
    """SHOM sends every S-57 attribute, mostly null. Nulls carry no information — drop them."""
    return {key: value for key, value in raw.items() if value not in (None, "")}


def _nav_aid_feature(record: NavAidRecord) -> dict[str, Any]:
    return _feature(
        _point(record.lon, record.lat),
        {
            "balise": "nav_aid",
            "source_id": record.source_id,
            "external_id": record.external_id,
            "inspire_id": record.inspire_id,
            "s57_class": record.s57_class,
            "name": record.name,
            "colour": record.colour,
            "colour_pattern": record.colour_pattern,
            "shape": record.shape,
            "topmark": record.topmark,
            "category": record.category,
            "light": record.light,
            "height_m": str(record.height_m) if record.height_m is not None else None,
            "raw": _compact(record.raw),
        },
    )


def _harbour_feature(record: HarbourRecord) -> dict[str, Any]:
    return _feature(
        _point(record.lon, record.lat),
        {
            "balise": "harbour",
            "source_id": record.source_id,
            "external_id": record.external_id,
            "slug": record.slug,
            "name": record.name,
            "vhf_channel": record.vhf_channel,
            "phone": record.phone,
            "website": record.website,
            "opening_hours": record.opening_hours,
            "services": list(record.services),
            "attrs_provenance": record.attrs_provenance,
        },
    )


def _field_feature(record: FieldRecord) -> dict[str, Any]:
    return _feature(
        record.area_geojson,
        {
            "balise": "field",
            "source_id": record.source_id,
            "external_id": record.external_id,
            "kind": record.kind.value,
            "name": record.name,
            "capacity": record.capacity,
            "visitor_capacity": record.visitor_capacity,
            "operator": record.operator,
            "price_per_night_cents": record.price_per_night_cents,
            "price_note": record.price_note,
        },
    )


def _spot_feature(record: SpotRecord) -> dict[str, Any]:
    return _feature(
        _point(record.lon, record.lat),
        {
            "balise": "spot",
            "source_id": record.source_id,
            "external_id": record.external_id,
            "kind": record.kind.value,
            "code": record.code,
            "depth_m": str(record.depth_m) if record.depth_m is not None else None,
            "max_loa_m": str(record.max_loa_m) if record.max_loa_m is not None else None,
            "max_draft_m": str(record.max_draft_m) if record.max_draft_m is not None else None,
            "holding": record.holding,
            "visitor": record.visitor,
            "attrs_provenance": record.attrs_provenance,
        },
    )


def _features(batch: NormalisedBatch, caps: Caps) -> list[dict[str, Any]]:
    fields = [record for record in batch.fields if record.area_geojson][: caps.fields]
    return [
        *(_nav_aid_feature(record) for record in batch.nav_aids[: caps.nav_aids]),
        *(_harbour_feature(record) for record in batch.harbours[: caps.harbours]),
        *(_field_feature(record) for record in fields),
        *(_spot_feature(record) for record in batch.spots[: caps.spots]),
    ]


def build(bbox_raw: str, name: str = "morbihan", caps: Caps = Caps()) -> dict[str, Any]:
    box = shom.Bbox.parse(bbox_raw)
    features: list[dict[str, Any]] = []
    for group in ("balisage", "ports", "reglementation"):
        layers = asyncio.run(shom.fetch_group(group, box))
        batch = shom_normaliser.normalise(group, layers, shom.SOURCES[group])
        features.extend(_features(batch, caps))
    overpass_features = osm.fetch_overpass(
        (box.min_lat, box.min_lon, box.max_lat, box.max_lon), None
    )
    features.extend(_features(osm_normaliser.normalise(overpass_features), caps))
    return {
        "type": "FeatureCollection",
        "meta": {
            "name": name,
            "bbox": bbox_raw,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "attribution": [
                "Shom, 2026 (Licence Ouverte Etalab 2.0)",
                "© les contributeurs OpenStreetMap (ODbL 1.0)",
            ],
        },
        "features": features,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox", default=DEFAULT_BBOX)
    parser.add_argument("--name", default="morbihan")
    parser.add_argument("--no-caps", action="store_true", help="Extract complet, sans plafonds")
    parser.add_argument("--out", type=Path, default=FIXTURE)
    arguments = parser.parse_args()
    payload = build(arguments.bbox, arguments.name, UNCAPPED if arguments.no_caps else Caps())
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_default) + "\n",
        encoding="utf-8",
    )
    logger.info("fixture écrite: %s (%d objets)", arguments.out, len(payload["features"]))


def _default(value: Any) -> Any:
    return asdict(value) if is_dataclass(value) and not isinstance(value, type) else str(value)


if __name__ == "__main__":
    main()
