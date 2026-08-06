"""Idempotent upserts keyed on `external_ids` — never on geometry (docs/05 ID strategy)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from balise_ingest.conflate import wins
from balise_ingest.records import (
    FieldRecord,
    HarbourRecord,
    NavAidRecord,
    SourceRecord,
    SpotRecord,
)


def _jsonb(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False)


def upsert_source(session: Session, source: SourceRecord) -> None:
    session.execute(
        text(
            """
            INSERT INTO source (id, kind, licence, attribution, url, last_sync_at)
            VALUES (:id, CAST(:kind AS source_kind), :licence, :attribution, :url, now())
            ON CONFLICT (id) DO UPDATE SET licence = EXCLUDED.licence,
                attribution = EXCLUDED.attribution, url = EXCLUDED.url, last_sync_at = now()
            """
        ),
        {
            "id": source.id,
            "kind": source.kind,
            "licence": source.licence,
            "attribution": source.attribution,
            "url": source.url,
        },
    )


def find_by_external(session: Session, table: str, source_id: str, external_id: str) -> int | None:
    row = session.execute(
        text(f"SELECT id FROM {table} WHERE external_ids ->> :source = :external LIMIT 1"),
        {"source": source_id, "external": external_id},
    ).scalar_one_or_none()
    return int(row) if row is not None else None


def merge_attributes(
    incoming: dict[str, Any],
    existing: dict[str, Any],
    provenance: dict[str, str],
    incoming_source: str,
    fallback_source: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Per-attribute source priority (docs/10). A weaker source never overwrites a stronger one."""
    updates: dict[str, Any] = {}
    new_provenance = dict(provenance)
    for attribute, value in incoming.items():
        if value in (None, "", (), []):
            continue
        current = existing.get(attribute)
        owner = provenance.get(attribute, fallback_source)
        if current in (None, "", (), []) or wins(attribute, incoming_source, owner):
            updates[attribute] = value
            new_provenance[attribute] = incoming_source
    return updates, new_provenance


def unique_slug(session: Session, slug: str) -> str:
    row = session.execute(
        text(
            """
            SELECT count(*) FROM harbour
            WHERE slug = :slug OR slug LIKE :prefix
            """
        ),
        {"slug": slug, "prefix": f"{slug}-%"},
    ).scalar_one()
    return slug if int(row) == 0 else f"{slug}-{int(row) + 1}"


def insert_harbour(session: Session, record: HarbourRecord) -> int:
    row = session.execute(
        text(
            """
            INSERT INTO harbour (slug, name, insee_code, geom, vhf_channel, phone, email, website,
                opening_hours, services, source_id, external_ids, attrs_provenance)
            VALUES (:slug, :name, :insee_code,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :vhf_channel, :phone, :email,
                    :website, :opening_hours, :services, :source_id,
                    CAST(:external_ids AS jsonb), CAST(:attrs_provenance AS jsonb))
            RETURNING id
            """
        ),
        {
            "slug": unique_slug(session, record.slug),
            "name": record.name,
            "insee_code": record.insee_code,
            "lon": record.lon,
            "lat": record.lat,
            "vhf_channel": record.vhf_channel,
            "phone": record.phone,
            "email": record.email,
            "website": record.website,
            "opening_hours": record.opening_hours,
            "services": list(record.services),
            "source_id": record.source_id,
            "external_ids": _jsonb({record.source_id: record.external_id}),
            "attrs_provenance": _jsonb(record.attrs_provenance),
        },
    ).scalar_one()
    return int(row)


def update_harbour(session: Session, harbour_id: int, record: HarbourRecord) -> None:
    existing = session.execute(
        text(
            """
            SELECT name, insee_code, vhf_channel, phone, email, website, opening_hours, services,
                   external_ids, attrs_provenance, source_id
            FROM harbour WHERE id = :id
            """
        ),
        {"id": harbour_id},
    ).one()
    incoming = {
        "name": record.name,
        "insee_code": record.insee_code,
        "vhf_channel": record.vhf_channel,
        "phone": record.phone,
        "email": record.email,
        "website": record.website,
        "opening_hours": record.opening_hours,
    }
    updates, provenance = merge_attributes(
        incoming,
        dict(existing._mapping),
        dict(existing.attrs_provenance or {}),
        record.source_id,
        existing.source_id,
    )
    services = sorted({*(existing.services or []), *record.services})
    external_ids = {**(existing.external_ids or {}), record.source_id: record.external_id}
    assignments = ", ".join(f"{column} = :{column}" for column in updates)
    prefix = f"{assignments}, " if assignments else ""
    session.execute(
        text(
            f"""
            UPDATE harbour SET {prefix}services = :services,
                external_ids = CAST(:external_ids AS jsonb),
                attrs_provenance = CAST(:attrs_provenance AS jsonb),
                updated_at = now()
            WHERE id = :id
            """
        ),
        {
            **updates,
            "id": harbour_id,
            "services": services,
            "external_ids": _jsonb(external_ids),
            "attrs_provenance": _jsonb(provenance),
        },
    )


def upsert_field(session: Session, record: FieldRecord, harbour_id: int | None) -> tuple[int, bool]:
    existing = find_by_external(session, "field", record.source_id, record.external_id)
    params = {
        "harbour_id": harbour_id,
        "name": record.name,
        "kind": record.kind.value,
        "area": _jsonb(record.area_geojson) if record.area_geojson else None,
        "capacity": record.capacity,
        "visitor_capacity": record.visitor_capacity,
        "operator": record.operator,
        "price_per_night_cents": record.price_per_night_cents,
        "price_note": record.price_note,
        "source_id": record.source_id,
        "external_ids": _jsonb({record.source_id: record.external_id}),
    }
    if existing is None:
        row = session.execute(
            text(
                """
                INSERT INTO field (harbour_id, name, kind, area, capacity, visitor_capacity,
                    operator, price_per_night_cents, price_note, source_id, external_ids)
                VALUES (:harbour_id, :name, CAST(:kind AS spot_kind),
                    CASE WHEN CAST(:area AS text) IS NULL THEN NULL ELSE
                      ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(CAST(:area AS text)), 4326)) END,
                    :capacity, :visitor_capacity, :operator, :price_per_night_cents, :price_note,
                    :source_id, CAST(:external_ids AS jsonb))
                RETURNING id
                """
            ),
            params,
        ).scalar_one()
        return int(row), True
    session.execute(
        text(
            """
            UPDATE field SET harbour_id = COALESCE(:harbour_id, harbour_id),
                name = COALESCE(:name, name), capacity = COALESCE(:capacity, capacity),
                visitor_capacity = COALESCE(:visitor_capacity, visitor_capacity),
                operator = COALESCE(:operator, operator),
                price_per_night_cents = COALESCE(:price_per_night_cents, price_per_night_cents),
                price_note = COALESCE(:price_note, price_note),
                area = CASE WHEN CAST(:area AS text) IS NULL THEN area ELSE
                  ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(CAST(:area AS text)), 4326)) END,
                updated_at = now()
            WHERE id = :id
            """
        ),
        {**params, "id": existing},
    )
    return existing, False


_SPOT_COLUMNS = (
    "code",
    "depth_m",
    "max_loa_m",
    "max_beam_m",
    "max_draft_m",
    "holding",
    "visitor",
    "bookable",
)


def insert_spot(
    session: Session, record: SpotRecord, field_id: int | None, harbour_id: int | None
) -> int:
    row = session.execute(
        text(
            """
            INSERT INTO spot (field_id, harbour_id, kind, code, geom, depth_m, max_loa_m,
                max_beam_m, max_draft_m, holding, exposure, visitor, bookable, source_id,
                external_ids, attrs_provenance)
            VALUES (:field_id, :harbour_id, CAST(:kind AS spot_kind), :code,
                ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :depth_m, :max_loa_m, :max_beam_m,
                :max_draft_m, :holding, :exposure, :visitor, :bookable, :source_id,
                CAST(:external_ids AS jsonb), CAST(:attrs_provenance AS jsonb))
            RETURNING id
            """
        ),
        {
            "field_id": field_id,
            "harbour_id": harbour_id,
            "kind": record.kind.value,
            "code": record.code,
            "lon": record.lon,
            "lat": record.lat,
            "depth_m": record.depth_m,
            "max_loa_m": record.max_loa_m,
            "max_beam_m": record.max_beam_m,
            "max_draft_m": record.max_draft_m,
            "holding": record.holding,
            "exposure": list(record.exposure),
            "visitor": record.visitor,
            "bookable": record.bookable,
            "source_id": record.source_id,
            "external_ids": _jsonb({record.source_id: record.external_id}),
            "attrs_provenance": _jsonb(record.attrs_provenance),
        },
    ).scalar_one()
    return int(row)


def merge_spot(
    session: Session, spot_id: int, record: SpotRecord, field_id: int | None, harbour_id: int | None
) -> dict[str, Any]:
    existing = session.execute(
        text(
            f"""
            SELECT {", ".join(_SPOT_COLUMNS)}, external_ids, attrs_provenance, source_id
            FROM spot WHERE id = :id
            """
        ),
        {"id": spot_id},
    ).one()
    incoming = {column: getattr(record, column, None) for column in _SPOT_COLUMNS}
    updates, provenance = merge_attributes(
        incoming,
        dict(existing._mapping),
        dict(existing.attrs_provenance or {}),
        record.source_id,
        existing.source_id,
    )
    position_owner = (existing.attrs_provenance or {}).get("position", existing.source_id)
    external_ids = {**(existing.external_ids or {}), record.source_id: record.external_id}
    assignments = [f"{column} = :{column}" for column in updates]
    if wins("position", record.source_id, position_owner):
        assignments.append("geom = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)")
        provenance["position"] = record.source_id
    session.execute(
        text(
            f"""
            UPDATE spot SET {
                ", ".join(
                    [
                        *assignments,
                        "field_id = COALESCE(:field_id, field_id)",
                        "harbour_id = COALESCE(:harbour_id, harbour_id)",
                        "external_ids = CAST(:external_ids AS jsonb)",
                        "attrs_provenance = CAST(:attrs_provenance AS jsonb)",
                        "missing_runs = 0",
                        "active = true",
                        "updated_at = now()",
                    ]
                )
            }
            WHERE id = :id
            """
        ),
        {
            **updates,
            "id": spot_id,
            "lon": record.lon,
            "lat": record.lat,
            "field_id": field_id,
            "harbour_id": harbour_id,
            "external_ids": _jsonb(external_ids),
            "attrs_provenance": _jsonb(provenance),
        },
    )
    return updates


def upsert_nav_aid(session: Session, record: NavAidRecord) -> tuple[int, bool]:
    # `inspire_id` doubles as the universal external key: SHOM ids are used as-is, other sources
    # are namespaced (`osm:node/123`) so re-runs stay idempotent.
    params = {
        "inspire_id": record.inspire_id or f"{record.source_id}:{record.external_id}",
        "s57_class": record.s57_class,
        "lon": record.lon,
        "lat": record.lat,
        "name": record.name,
        "colour": record.colour,
        "colour_pattern": record.colour_pattern,
        "shape": record.shape,
        "topmark": record.topmark,
        "category": record.category,
        "light": _jsonb(record.light) if record.light else None,
        "height_m": record.height_m,
        "source_id": record.source_id,
        "raw": _jsonb(record.raw),
    }
    row = session.execute(
        text(
            """
            INSERT INTO nav_aid (inspire_id, s57_class, geom, name, colour, colour_pattern, shape,
                topmark, category, light, height_m, source_id, raw, active)
            VALUES (:inspire_id, :s57_class, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :name,
                :colour, :colour_pattern, :shape, :topmark, :category, CAST(:light AS jsonb),
                :height_m, :source_id, CAST(:raw AS jsonb), true)
            ON CONFLICT (inspire_id) DO UPDATE SET
                geom = EXCLUDED.geom, name = EXCLUDED.name, colour = EXCLUDED.colour,
                colour_pattern = EXCLUDED.colour_pattern, shape = EXCLUDED.shape,
                topmark = EXCLUDED.topmark, category = EXCLUDED.category, light = EXCLUDED.light,
                height_m = EXCLUDED.height_m, raw = EXCLUDED.raw, active = true,
                updated_at = now()
            RETURNING id, xmax = 0 AS inserted
            """
        ),
        params,
    ).one()
    return int(row.id), bool(row.inserted)
