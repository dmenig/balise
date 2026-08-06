"""Staging tables, one per provenance (docs/04 §2, docs/10).

Raw features land here before conflation so a rule change can be re-derived from the database
without re-fetching, and so ODbL-derived rows never mix with anything else.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from balise_ingest.records import RawFeature

TABLES = {"shom": "shom_feature", "osm": "osm_feature", "zmel": "zmel_feature"}


def table_for(source_id: str) -> str:
    prefix = source_id.split(".")[0]
    table = TABLES.get(prefix)
    if table is None:
        raise KeyError(f"pas de table de staging pour la source {source_id!r}")
    return table


def write(
    session: Session, source_id: str, features: list[RawFeature], snapshot_date: str | None = None
) -> int:
    table = table_for(source_id)
    day = snapshot_date or datetime.now(UTC).date().isoformat()
    rows: list[dict[str, Any]] = [
        {
            "external_id": feature.external_id,
            "layer": feature.layer,
            "geometry": json.dumps(feature.geometry) if feature.geometry else None,
            "properties": json.dumps(feature.properties, default=str, ensure_ascii=False),
            "snapshot_date": day,
        }
        for feature in features
    ]
    if not rows:
        return 0
    session.execute(
        text(
            f"""
            INSERT INTO {table} (external_id, layer, geom, properties, snapshot_date, fetched_at)
            VALUES (:external_id, :layer,
                    CASE WHEN CAST(:geometry AS text) IS NULL THEN NULL
                         ELSE ST_SetSRID(ST_GeomFromGeoJSON(CAST(:geometry AS text)), 4326) END,
                    CAST(:properties AS jsonb), :snapshot_date, now())
            ON CONFLICT (layer, external_id) DO UPDATE SET
                geom = EXCLUDED.geom, properties = EXCLUDED.properties,
                snapshot_date = EXCLUDED.snapshot_date, fetched_at = now()
            """
        ),
        rows,
    )
    return len(rows)


def read(session: Session, source_id: str, layer: str | None = None) -> list[RawFeature]:
    table = table_for(source_id)
    clause = "WHERE layer = :layer" if layer else ""
    rows = session.execute(
        text(
            f"""
            SELECT external_id, layer, ST_AsGeoJSON(geom) AS geometry, properties
            FROM {table} {clause}
            """
        ),
        {"layer": layer} if layer else {},
    ).all()
    return [
        RawFeature(
            external_id=row.external_id,
            layer=row.layer,
            geometry=json.loads(row.geometry) if row.geometry else None,
            properties=dict(row.properties),
        )
        for row in rows
    ]
