"""`make seed` — a working Morbihan map with no network access at all (docs/11).

The fixture keeps each object's real `source_id`, so provenance and the ODbL separation stay
honest even in development.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from balise_api.auth.tokens import issue_feed_token
from balise_api.db import sync_session
from balise_api.domain.enums import SpotKind
from sqlalchemy import text

from balise_ingest.load import load_batch
from balise_ingest.records import (
    FieldRecord,
    HarbourRecord,
    NavAidRecord,
    NormalisedBatch,
    SourceRecord,
    SpotRecord,
)

FIXTURE = Path(__file__).parent / "fixtures" / "morbihan.geojson"
DEMO_FEED_ID = "feed.demo-morbihan"
logger = logging.getLogger(__name__)

_LICENCES = {
    "shom.balisage": ("etalab-2.0", "Shom, 2026 (Licence Ouverte Etalab 2.0)"),
    "shom.ports": ("etalab-2.0", "Shom, 2026 (Licence Ouverte Etalab 2.0)"),
    "shom.reglementation": ("etalab-2.0", "Shom, 2026 (Licence Ouverte Etalab 2.0)"),
    "osm": ("odbl-1.0", "© les contributeurs OpenStreetMap (ODbL 1.0)"),
}


def _decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _point(feature: dict[str, Any]) -> tuple[float, float]:
    coordinates = feature["geometry"]["coordinates"]
    return float(coordinates[0]), float(coordinates[1])


def _source(source_id: str) -> SourceRecord:
    licence, attribution = _LICENCES.get(source_id, ("etalab-2.0", source_id))
    return SourceRecord(id=source_id, kind="import", licence=licence, attribution=attribution)


def _record(feature: dict[str, Any]) -> tuple[str, str, object]:
    properties = feature["properties"]
    kind = properties["balise"]
    source_id = properties["source_id"]
    external_id = properties["external_id"]
    if kind == "nav_aid":
        lon, lat = _point(feature)
        return (
            source_id,
            kind,
            NavAidRecord(
                external_id=external_id,
                source_id=source_id,
                s57_class=properties["s57_class"],
                lon=lon,
                lat=lat,
                inspire_id=properties.get("inspire_id"),
                name=properties.get("name"),
                colour=properties.get("colour"),
                colour_pattern=properties.get("colour_pattern"),
                shape=properties.get("shape"),
                topmark=properties.get("topmark"),
                category=properties.get("category"),
                light=properties.get("light"),
                height_m=_decimal(properties.get("height_m")),
                raw=properties.get("raw", {}),
            ),
        )
    if kind == "harbour":
        lon, lat = _point(feature)
        return (
            source_id,
            kind,
            HarbourRecord(
                external_id=external_id,
                source_id=source_id,
                slug=properties["slug"],
                name=properties["name"],
                lon=lon,
                lat=lat,
                vhf_channel=properties.get("vhf_channel"),
                phone=properties.get("phone"),
                website=properties.get("website"),
                opening_hours=properties.get("opening_hours"),
                services=tuple(properties.get("services", [])),
                attrs_provenance=properties.get("attrs_provenance", {}),
            ),
        )
    if kind == "field":
        return (
            source_id,
            kind,
            FieldRecord(
                external_id=external_id,
                source_id=source_id,
                kind=SpotKind(properties["kind"]),
                name=properties.get("name"),
                harbour_external_id=properties.get("harbour_external_id"),
                capacity=properties.get("capacity"),
                visitor_capacity=properties.get("visitor_capacity"),
                operator=properties.get("operator"),
                price_per_night_cents=properties.get("price_per_night_cents"),
                price_note=properties.get("price_note"),
                area_geojson=feature.get("geometry"),
            ),
        )
    lon, lat = _point(feature)
    return (
        source_id,
        "spot",
        SpotRecord(
            external_id=external_id,
            source_id=source_id,
            kind=SpotKind(properties["kind"]),
            lon=lon,
            lat=lat,
            code=properties.get("code"),
            field_external_id=properties.get("field_external_id"),
            harbour_external_id=properties.get("harbour_external_id"),
            depth_m=_decimal(properties.get("depth_m")),
            max_loa_m=_decimal(properties.get("max_loa_m")),
            max_draft_m=_decimal(properties.get("max_draft_m")),
            holding=properties.get("holding"),
            exposure=tuple(properties.get("exposure", [])),
            visitor=bool(properties.get("visitor", False)),
            attrs_provenance=properties.get(
                "attrs_provenance", {"position": properties["source_id"]}
            ),
        ),
    )


def batches(path: Path) -> list[NormalisedBatch]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    grouped: dict[str, dict[str, list[Any]]] = defaultdict(
        lambda: {"nav_aid": [], "harbour": [], "field": [], "spot": []}
    )
    for feature in payload["features"]:
        source_id, kind, record = _record(feature)
        grouped[source_id][kind].append(record)
    return [
        NormalisedBatch(
            source=_source(source_id),
            nav_aids=tuple(records["nav_aid"]),
            harbours=tuple(records["harbour"]),
            fields=tuple(records["field"]),
            spots=tuple(records["spot"]),
        )
        for source_id, records in grouped.items()
    ]


def create_demo_feed(session: Any, harbour_id: int) -> str:
    token, token_hash = issue_feed_token(DEMO_FEED_ID)
    session.execute(
        text(
            """
            INSERT INTO feed (id, harbour_id, kind, contact_email, token_hash, ttl_seconds, trust)
            VALUES (:id, :harbour_id, 'port_feed', 'capitainerie@example.test',
                    :token_hash, 60, 0.95)
            ON CONFLICT (id) DO UPDATE SET harbour_id = EXCLUDED.harbour_id,
                token_hash = EXCLUDED.token_hash, active = true
            """
        ),
        {"id": DEMO_FEED_ID, "harbour_id": harbour_id, "token_hash": token_hash},
    )
    return token


def seed(fixture: Path | None = None, *, with_demo_feed: bool = False) -> dict[str, object]:
    path = fixture or FIXTURE
    if not path.exists():
        raise FileNotFoundError(
            f"fixture absente: {path} — générer avec `uv run python -m balise_ingest.make_fixture`"
        )
    reports: list[dict[str, object]] = []
    with sync_session() as session:
        for batch in batches(path):
            report = load_batch(session, batch, force=True)
            reports.append(report.as_dict())
        # 🔌 The demo MBFS feed belongs to v2: a v1 database keeps every availability table empty
        # (docs/06 §A/S1), so this only happens when a developer asks for it explicitly.
        harbour_id = (
            session.execute(text("SELECT id FROM harbour ORDER BY id LIMIT 1")).scalar_one_or_none()
            if with_demo_feed
            else None
        )
        token = create_demo_feed(session, int(harbour_id)) if harbour_id else None
        session.commit()
    return {
        "stage": "seed",
        "fixture": str(path),
        "loads": reports,
        "demo_feed": {"id": DEMO_FEED_ID, "token": token} if token else None,
    }
