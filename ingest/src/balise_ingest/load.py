"""Load stage (docs/10): one transaction per source per run, idempotent, with the guards that
keep a broken upstream from emptying the map.

Never delete on absence. Never promote a run whose counts moved more than 20 %.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from balise_ingest import conflate, upserts
from balise_ingest.overrides import Overrides
from balise_ingest.records import NormalisedBatch, ServicePoint, SpmPort

ANOMALY_THRESHOLD = 0.20
MISSING_RUNS_BEFORE_DEACTIVATION = 3
SERVICE_ATTACH_RADIUS_M = 500.0
SPM_ATTACH_RADIUS_M = 12_000.0
FIELD_ATTACH_RADIUS_M = 800.0

logger = logging.getLogger(__name__)


class CountAnomaly(RuntimeError):
    """Counts moved > 20 % versus the previous run — block promotion, require --force."""


@dataclass
class LoadReport:
    source_id: str
    run_id: str
    inserted: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)
    conflated: int = 0
    rejected: int = 0
    deactivated: int = 0
    ref_version: int = 0
    linked: dict[str, int] = field(default_factory=dict)

    def bump(self, bucket: dict[str, int], key: str) -> None:
        bucket[key] = bucket.get(key, 0) + 1

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "run_id": self.run_id,
            "inserted": self.inserted,
            "updated": self.updated,
            "conflated": self.conflated,
            "rejected": self.rejected,
            "deactivated": self.deactivated,
            "linked": self.linked,
            "ref_version": self.ref_version,
        }


def _previous_counts(session: Session, source_id: str) -> dict[str, int]:
    raw = session.execute(
        text("SELECT value FROM meta WHERE key = :key"), {"key": f"counts:{source_id}"}
    ).scalar_one_or_none()
    return dict(json.loads(raw)) if raw else {}


def _store_counts(session: Session, source_id: str, counts: dict[str, int]) -> None:
    session.execute(
        text(
            """
            INSERT INTO meta (key, value, updated_at) VALUES (:key, :value, now())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """
        ),
        {"key": f"counts:{source_id}", "value": json.dumps(counts)},
    )


def check_anomaly(previous: dict[str, int], current: dict[str, int]) -> str | None:
    for key, previous_count in previous.items():
        if previous_count < 50:
            continue
        delta = abs(current.get(key, 0) - previous_count) / previous_count
        if delta > ANOMALY_THRESHOLD:
            return f"{key}: {previous_count} → {current.get(key, 0)} ({delta:.0%})"
    return None


def bump_ref_version(session: Session) -> int:
    row = session.execute(
        text(
            """
            UPDATE meta SET value = (CAST(value AS bigint) + 1)::text, updated_at = now()
            WHERE key = 'ref_version' RETURNING value
            """
        )
    ).scalar_one()
    return int(row)


def _harbour_for_point(session: Session, lon: float, lat: float, radius_m: float) -> int | None:
    return session.execute(
        text(
            """
            SELECT id FROM harbour
            WHERE ST_DWithin(geom::geography,
                             ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius)
            ORDER BY geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
            LIMIT 1
            """
        ),
        {"lon": lon, "lat": lat, "radius": radius_m},
    ).scalar_one_or_none()


def _field_for_point(session: Session, lon: float, lat: float) -> int | None:
    return session.execute(
        text(
            """
            SELECT id FROM field
            WHERE area IS NOT NULL
              AND ST_Contains(area, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
            LIMIT 1
            """
        ),
        {"lon": lon, "lat": lat},
    ).scalar_one_or_none()


def link_orphans(session: Session) -> dict[str, int]:
    """Attach spots and fields whose parent did not exist yet when they were loaded.

    Sources arrive in whatever order the schedule fires them (SHOM weekly, OSM daily), so
    parenting must not depend on load order — it is recomputed for orphans on every run.
    """
    spots_to_harbour = session.execute(
        text(
            """
            UPDATE spot s SET harbour_id = nearest.id, updated_at = now()
            FROM (
              SELECT s2.id AS spot_id, (
                SELECT h.id FROM harbour h
                WHERE ST_DWithin(h.geom::geography, s2.geom::geography, :radius)
                ORDER BY h.geom <-> s2.geom LIMIT 1
              ) AS id
              FROM spot s2 WHERE s2.harbour_id IS NULL AND s2.active
            ) nearest
            WHERE s.id = nearest.spot_id AND nearest.id IS NOT NULL
            RETURNING s.id
            """
        ),
        {"radius": FIELD_ATTACH_RADIUS_M},
    )
    linked_spots = len(spots_to_harbour.scalars().all())

    spots_to_field = session.execute(
        text(
            """
            UPDATE spot s SET field_id = f.id, updated_at = now()
            FROM field f
            WHERE s.field_id IS NULL AND s.active AND f.area IS NOT NULL
              AND f.kind = s.kind AND ST_Contains(f.area, s.geom)
            RETURNING s.id
            """
        )
    )
    linked_fields = len(spots_to_field.scalars().all())

    fields_to_harbour = session.execute(
        text(
            """
            UPDATE field f SET harbour_id = nearest.id, updated_at = now()
            FROM (
              SELECT f2.id AS field_id, (
                SELECT h.id FROM harbour h
                WHERE f2.area IS NOT NULL
                  AND ST_DWithin(h.geom::geography, f2.area::geography, :radius)
                ORDER BY h.geom <-> ST_Centroid(f2.area) LIMIT 1
              ) AS id
              FROM field f2 WHERE f2.harbour_id IS NULL
            ) nearest
            WHERE f.id = nearest.field_id AND nearest.id IS NOT NULL
            RETURNING f.id
            """
        ),
        {"radius": FIELD_ATTACH_RADIUS_M},
    )
    return {
        "spots_to_harbour": linked_spots,
        "spots_to_field": linked_fields,
        "fields_to_harbour": len(fields_to_harbour.scalars().all()),
    }


def _attach_services(session: Session, points: tuple[ServicePoint, ...]) -> int:
    attached = 0
    for point in points:
        harbour_id = _harbour_for_point(session, point.lon, point.lat, SERVICE_ATTACH_RADIUS_M)
        if harbour_id is None:
            continue
        session.execute(
            text(
                """
                UPDATE harbour
                SET services = (
                      SELECT array_agg(DISTINCT service ORDER BY service)
                      FROM unnest(array_append(services, :service)) AS service
                    ),
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"service": point.service, "id": harbour_id},
        )
        attached += 1
    return attached


def _attach_spm_ports(session: Session, ports: tuple[SpmPort, ...]) -> int:
    attached = 0
    for port in ports:
        harbour_id = _harbour_for_point(session, port.lon, port.lat, SPM_ATTACH_RADIUS_M)
        if harbour_id is None:
            continue
        session.execute(
            text(
                """
                UPDATE harbour
                SET external_ids = external_ids
                                   || jsonb_build_object('shom_spm', CAST(:key AS text)),
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"key": port.key, "id": harbour_id},
        )
        attached += 1
    return attached


def _deactivate_missing(session: Session, source_id: str, seen: set[str]) -> int:
    """Three consecutive absences from an authoritative source, never on the first (docs/10)."""
    session.execute(
        text(
            """
            UPDATE spot SET missing_runs = missing_runs + 1, updated_at = now()
            WHERE source_id = :source_id AND active
              AND NOT (external_ids ->> :source_id = ANY(:seen))
            """
        ),
        {"source_id": source_id, "seen": sorted(seen) or [""]},
    )
    deactivated = session.execute(
        text(
            """
            UPDATE spot SET active = false, updated_at = now()
            WHERE source_id = :source_id AND active AND missing_runs >= :threshold
            RETURNING id
            """
        ),
        {"source_id": source_id, "threshold": MISSING_RUNS_BEFORE_DEACTIVATION},
    )
    return len(deactivated.scalars().all())


def load_batch(
    session: Session,
    batch: NormalisedBatch,
    *,
    run_id: str | None = None,
    overrides: Overrides | None = None,
    force: bool = False,
) -> LoadReport:
    overrides = overrides or Overrides.load()
    batch = overrides.apply(batch)
    run_id = run_id or f"{batch.source.id}:{datetime.now(UTC).isoformat(timespec='seconds')}"
    report = LoadReport(source_id=batch.source.id, run_id=run_id)

    previous = _previous_counts(session, batch.source.id)
    anomaly = check_anomaly(previous, batch.counts())
    if anomaly and not force:
        raise CountAnomaly(
            f"{batch.source.id}: variation > {ANOMALY_THRESHOLD:.0%} ({anomaly}); "
            "données précédentes conservées, relancer avec --force après vérification"
        )
    if anomaly:
        logger.warning("anomalie de comptage forcée: %s", anomaly)

    upserts.upsert_source(session, batch.source)
    harbour_ids: dict[str, int] = {}
    for harbour in batch.harbours:
        existing = upserts.find_by_external(
            session, "harbour", harbour.source_id, harbour.external_id
        )
        match = (
            None
            if existing
            else conflate.match_harbour(session, harbour.lon, harbour.lat, harbour.name)
        )
        target = existing or (match.row_id if match else None)
        if target is None:
            target = upserts.insert_harbour(session, harbour)
            report.bump(report.inserted, "harbours")
        else:
            upserts.update_harbour(session, target, harbour)
            report.bump(report.updated, "harbours")
            if match is not None:
                report.conflated += 1
        conflate.log_decision(
            session,
            run_id=run_id,
            target_table="harbour",
            target_id=target,
            left_source_id=harbour.source_id,
            left_external_id=harbour.external_id,
            match=match,
            rule=match.rule if match else "insert",
        )
        harbour_ids[harbour.external_id] = target

    field_ids: dict[str, int] = {}
    for field_record in batch.fields:
        harbour_id = (
            harbour_ids.get(field_record.harbour_external_id or "")
            if field_record.harbour_external_id
            else None
        )
        target, inserted = upserts.upsert_field(session, field_record, harbour_id)
        field_ids[field_record.external_id] = target
        report.bump(report.inserted if inserted else report.updated, "fields")

    seen_external: set[str] = set()
    for spot in batch.spots:
        seen_external.add(spot.external_id)
        existing = upserts.find_by_external(session, "spot", spot.source_id, spot.external_id)
        match = None if existing else conflate.match_spot(session, spot, overrides)
        field_id = field_ids.get(spot.field_external_id or "") or _field_for_point(
            session, spot.lon, spot.lat
        )
        harbour_id = harbour_ids.get(spot.harbour_external_id or "") or _harbour_for_point(
            session, spot.lon, spot.lat, FIELD_ATTACH_RADIUS_M
        )
        if existing is not None:
            upserts.merge_spot(session, existing, spot, field_id, harbour_id)
            report.bump(report.updated, "spots")
            target = existing
        elif match is not None:
            upserts.merge_spot(session, match.row_id, spot, field_id, harbour_id)
            report.conflated += 1
            target = match.row_id
        else:
            target = upserts.insert_spot(session, spot, field_id, harbour_id)
            report.bump(report.inserted, "spots")
        conflate.log_decision(
            session,
            run_id=run_id,
            target_table="spot",
            target_id=target,
            left_source_id=spot.source_id,
            left_external_id=spot.external_id,
            match=match,
            rule=match.rule if match else ("update" if existing else "insert"),
            detail={"kind": spot.kind.value, "code": spot.code},
        )

    for nav_aid in batch.nav_aids:
        match = conflate.match_nav_aid(session, nav_aid)
        if match is not None and match.source_id.startswith("shom") and nav_aid.source_id == "osm":
            report.rejected += 1
            conflate.log_decision(
                session,
                run_id=run_id,
                target_table="nav_aid",
                target_id=match.row_id,
                left_source_id=nav_aid.source_id,
                left_external_id=nav_aid.external_id,
                match=match,
                rule="shom wins over osm for nav aids",
            )
            continue
        _, inserted = upserts.upsert_nav_aid(session, nav_aid)
        report.bump(report.inserted if inserted else report.updated, "nav_aids")

    report.deactivated = (
        _deactivate_missing(session, batch.source.id, seen_external) if batch.spots else 0
    )
    _attach_services(session, batch.service_points)
    _attach_spm_ports(session, batch.spm_ports)
    report.linked = link_orphans(session)
    _store_counts(session, batch.source.id, batch.counts())
    report.ref_version = bump_ref_version(session)
    logger.info("load %s", report.as_dict())
    return report
