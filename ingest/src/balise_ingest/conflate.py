"""Conflation (docs/10): the same mooring appears in OSM, sometimes in SHOM and in a ZMEL file,
each with a slightly different position. Decide when two rows are one object, and which source
wins per attribute. Every decision is logged — that is the only way to debug "why did my buoy move".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from balise_api.domain.enums import SpotKind
from sqlalchemy import text
from sqlalchemy.orm import Session

from balise_ingest.overrides import Overrides, Ref
from balise_ingest.records import NavAidRecord, SpotRecord

logger = logging.getLogger(__name__)

#: Match radius per kind. 25 m ≈ GPS + charting error for a buoy; a berth is 8 m wide.
TOLERANCE_M: dict[SpotKind, float] = {
    SpotKind.MOORING_BUOY: 25.0,
    SpotKind.BERTH: 8.0,
    SpotKind.PILE: 15.0,
    SpotKind.QUAY: 15.0,
    SpotKind.ANCHORAGE: 150.0,
}
NAV_AID_TOLERANCE_M = 25.0
HARBOUR_TOLERANCE_M = 400.0

#: Attribute-level source priority, best first. Matched by prefix on `source_id`.
PRIORITIES: dict[str, tuple[str, ...]] = {
    "navaid_position": ("shom.balisage", "osm"),
    "position": ("operator", "zmel", "osm", "shom"),
    "kind": ("operator", "zmel", "shom", "osm"),
    "name": ("operator", "osm", "shom"),
    "code": ("operator", "zmel", "osm", "shom"),
    "capacity": ("operator", "feed", "zmel", "osm"),
    "price": ("operator", "feed", "zmel", "osm"),
    "contacts": ("operator", "feed", "osm", "shom"),
    "depth_m": ("shom", "osm", "zmel"),
    "max_loa_m": ("operator", "feed", "osm", "zmel"),
    "max_draft_m": ("operator", "feed", "osm", "zmel"),
}
_ATTRIBUTE_GROUP = {
    "depth_m": "depth_m",
    "max_loa_m": "max_loa_m",
    "max_draft_m": "max_draft_m",
    "max_beam_m": "max_loa_m",
    "holding": "depth_m",
    "code": "code",
    "visitor": "capacity",
    "bookable": "capacity",
}


def rank(attribute_group: str, source_id: str) -> int:
    order = PRIORITIES[attribute_group]
    for index, prefix in enumerate(order):
        if source_id.startswith(prefix):
            return index
    return len(order)


def wins(attribute: str, candidate_source: str, incumbent_source: str) -> bool:
    group = _ATTRIBUTE_GROUP.get(attribute, "position")
    return rank(group, candidate_source) < rank(group, incumbent_source)


@dataclass(frozen=True, slots=True)
class Match:
    row_id: int
    source_id: str
    external_id: str | None
    distance_m: float
    rule: str


_SPOT_MATCH_SQL = """
SELECT s.id, s.source_id, s.code,
       ST_Distance(s.geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS d,
       s.external_ids
FROM spot s
WHERE s.kind = CAST(:kind AS spot_kind)
  AND ST_DWithin(s.geom::geography,
                 ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :tolerance)
ORDER BY d
LIMIT 5
"""

_NAV_AID_MATCH_SQL = """
SELECT n.id, n.source_id, n.inspire_id,
       ST_Distance(n.geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS d
FROM nav_aid n
WHERE n.s57_class = :s57_class
  AND ST_DWithin(n.geom::geography,
                 ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :tolerance)
ORDER BY d
LIMIT 1
"""

_HARBOUR_MATCH_SQL = """
SELECT h.id, h.source_id, h.slug,
       ST_Distance(h.geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS d,
       similarity(h.name, :name) AS name_similarity
FROM harbour h
WHERE ST_DWithin(h.geom::geography,
                 ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :tolerance)
ORDER BY d
LIMIT 5
"""


def _own_external_id(external_ids: dict[str, Any] | None, source_id: str) -> str | None:
    if not external_ids:
        return None
    value = external_ids.get(source_id)
    return str(value) if value is not None else None


def match_spot(session: Session, record: SpotRecord, overrides: Overrides) -> Match | None:
    """Same kind, within tolerance, and codes that do not contradict each other."""
    rows = session.execute(
        text(_SPOT_MATCH_SQL),
        {
            "kind": record.kind.value,
            "lon": record.lon,
            "lat": record.lat,
            "tolerance": TOLERANCE_M[record.kind],
        },
    ).all()
    forced = overrides.forced_merge_target(record.source_id, record.external_id)
    for row in rows:
        existing_external = _own_external_id(row.external_ids, row.source_id)
        if existing_external is not None and Ref(row.source_id, existing_external) == forced:
            return Match(
                row.id, row.source_id, existing_external, float(row.d), "override.force_merge"
            )
        if row.source_id == record.source_id:
            continue
        if existing_external is not None and overrides.is_forced_split(
            Ref(record.source_id, record.external_id), Ref(row.source_id, existing_external)
        ):
            continue
        if row.code and record.code and row.code.strip().lower() != record.code.strip().lower():
            continue
        return Match(
            row_id=row.id,
            source_id=row.source_id,
            external_id=existing_external,
            distance_m=float(row.d),
            rule=f"distance<={TOLERANCE_M[record.kind]:.0f}m,kind={record.kind.value}",
        )
    return None


def match_nav_aid(session: Session, record: NavAidRecord) -> Match | None:
    row = session.execute(
        text(_NAV_AID_MATCH_SQL),
        {
            "s57_class": record.s57_class,
            "lon": record.lon,
            "lat": record.lat,
            "tolerance": NAV_AID_TOLERANCE_M,
        },
    ).one_or_none()
    if row is None:
        return None
    return Match(
        row_id=row.id,
        source_id=row.source_id,
        external_id=row.inspire_id,
        distance_m=float(row.d),
        rule=f"navaid distance<={NAV_AID_TOLERANCE_M:.0f}m,class={record.s57_class}",
    )


def match_harbour(session: Session, lon: float, lat: float, name: str) -> Match | None:
    rows = session.execute(
        text(_HARBOUR_MATCH_SQL),
        {"lon": lon, "lat": lat, "name": name, "tolerance": HARBOUR_TOLERANCE_M},
    ).all()
    for row in rows:
        similarity = float(row.name_similarity or 0.0)
        if similarity < 0.35 and row.d > 150:
            continue
        return Match(
            row_id=row.id,
            source_id=row.source_id,
            external_id=row.slug,
            distance_m=float(row.d),
            rule=f"harbour distance<={HARBOUR_TOLERANCE_M:.0f}m,similarity={similarity:.2f}",
        )
    return None


def log_decision(
    session: Session,
    *,
    run_id: str,
    target_table: str,
    target_id: int | None,
    left_source_id: str,
    left_external_id: str,
    match: Match | None,
    rule: str,
    detail: dict[str, Any] | None = None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO conflation_log (run_id, target_table, target_id, left_source_id,
                left_external_id, right_source_id, right_external_id, distance_m, rule, detail)
            VALUES (:run_id, :target_table, :target_id, :left_source_id, :left_external_id,
                    :right_source_id, :right_external_id, :distance_m, :rule,
                    CAST(:detail AS jsonb))
            """
        ),
        {
            "run_id": run_id,
            "target_table": target_table,
            "target_id": target_id,
            "left_source_id": left_source_id,
            "left_external_id": left_external_id,
            "right_source_id": match.source_id if match else None,
            "right_external_id": match.external_id if match else None,
            "distance_m": round(match.distance_m, 2) if match else None,
            "rule": rule,
            "detail": _json(detail or {}),
        },
    )


def _json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, default=str, ensure_ascii=False)


def explain(session: Session, target_table: str, target_id: int) -> list[dict[str, Any]]:
    """`--explain spot_18421`: every decision that shaped this row.

    Read it before touching the rules.
    """
    rows = session.execute(
        text(
            """
            SELECT run_id, rule, left_source_id, left_external_id, right_source_id,
                   right_external_id, distance_m, detail, created_at
            FROM conflation_log
            WHERE target_table = :target_table AND target_id = :target_id
            ORDER BY created_at
            """
        ),
        {"target_table": target_table, "target_id": target_id},
    ).all()
    return [dict(row._mapping) for row in rows]
