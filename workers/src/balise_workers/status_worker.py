"""`balise-status-worker` — decay, feed health, environment refresh (docs/07).

The decay job exists because a status is a projection: nothing new arriving is itself information.
A port feed that went silent must go `unknown`, never stay green.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import typer
from apscheduler.schedulers.blocking import BlockingScheduler
from balise_api.db import sync_session
from balise_api.domain.enums import ReportKind, SourceKind, SpotKind, SpotState
from balise_api.domain.observation import ObservationInput
from balise_api.services.availability.reputation import effective_weight
from balise_api.services.availability.status import derive_status, observation_window
from balise_ingest.jobs import refresh_tides, refresh_weather
from sqlalchemy import text
from sqlalchemy.orm import Session

app = typer.Typer(add_completion=False, help="Worker de statut Balise")
logger = logging.getLogger("balise_workers.status")

DECAY_BATCH = 5000

_CANDIDATES_SQL = """
SELECT st.spot_id, s.kind::text AS kind
FROM spot_status st
JOIN spot s ON s.id = st.spot_id
WHERE st.state <> 'unknown'
  AND st.updated_at < now() - interval '2 minutes'
ORDER BY st.as_of
LIMIT :limit
"""

_OBSERVATIONS_SQL = """
SELECT o.id, o.state::text AS state, o.source_kind::text AS source_kind, o.observed_at,
       o.confidence, o.payload, o.source_ref, o.contributor_id,
       COALESCE(c.reputation, 1.0) AS reputation
FROM observation o
LEFT JOIN contributor c ON c.id = o.contributor_id
WHERE o.spot_id = :spot_id AND NOT o.suppressed AND o.observed_at >= :since
ORDER BY o.observed_at DESC
LIMIT 500
"""

_UPSERT_SQL = """
INSERT INTO spot_status (spot_id, state, confidence, as_of, source_kind, observation_id, updated_at)
VALUES (:spot_id, CAST(:state AS spot_state), :confidence, :as_of,
        CAST(:source_kind AS source_kind), :observation_id, now())
ON CONFLICT (spot_id) DO UPDATE SET state = EXCLUDED.state, confidence = EXCLUDED.confidence,
    as_of = EXCLUDED.as_of, source_kind = EXCLUDED.source_kind,
    observation_id = EXCLUDED.observation_id, updated_at = now()
"""

_FEED_STALE_SQL = """
SELECT f.id, f.ttl_seconds, f.last_seen_at
FROM feed f
WHERE f.active AND (f.last_seen_at IS NULL
                    OR f.last_seen_at < now() - make_interval(secs => 3 * f.ttl_seconds))
"""

_FEED_SPOTS_UNKNOWN_SQL = """
UPDATE spot_status st
SET state = 'unknown', confidence = 0, source_kind = 'port_feed', as_of = now(), updated_at = now()
WHERE st.state <> 'unknown'
  AND st.source_kind IN ('port_feed', 'sensor')
  AND st.spot_id IN (SELECT id FROM spot WHERE harbour_id = (
        SELECT harbour_id FROM feed WHERE id = :feed_id))
RETURNING st.spot_id
"""


@dataclass(frozen=True, slots=True)
class DecayReport:
    checked: int
    changed: int


def _to_input(row: object) -> ObservationInput:
    payload = getattr(row, "payload", {}) or {}
    raw_kind = payload.get("report_kind")
    return ObservationInput(
        id=int(row.id),  # type: ignore[attr-defined]
        state=SpotState(row.state),  # type: ignore[attr-defined]
        source_kind=SourceKind(row.source_kind),  # type: ignore[attr-defined]
        report_kind=ReportKind(raw_kind) if isinstance(raw_kind, str) else ReportKind.IMPORT,
        observed_at=row.observed_at,  # type: ignore[attr-defined]
        confidence=float(row.confidence),  # type: ignore[attr-defined]
        source_ref=row.source_ref,  # type: ignore[attr-defined]
        contributor_reputation=effective_weight(float(row.reputation)),  # type: ignore[attr-defined]
        contributor_id=row.contributor_id,  # type: ignore[attr-defined]
    )


def recompute_decay(
    session: Session, now: datetime | None = None, limit: int = DECAY_BATCH
) -> DecayReport:
    now = now or datetime.now(UTC)
    rows = session.execute(text(_CANDIDATES_SQL), {"limit": limit}).all()
    changed = 0
    for row in rows:
        kind = SpotKind(row.kind)
        since = now - observation_window(kind)
        observations = [
            _to_input(observation)
            for observation in session.execute(
                text(_OBSERVATIONS_SQL), {"spot_id": row.spot_id, "since": since}
            ).all()
        ]
        status = derive_status(kind, observations, now)
        session.execute(
            text(_UPSERT_SQL),
            {
                "spot_id": row.spot_id,
                "state": status.state.value,
                "confidence": round(status.confidence, 2),
                "as_of": status.as_of,
                "source_kind": status.source_kind.value,
                "observation_id": status.observation_id,
            },
        )
        session.execute(
            text("SELECT pg_notify('status_changed', :payload)"),
            {
                "payload": json.dumps(
                    {
                        "type": "status",
                        "spot_id": f"spot_{row.spot_id}",
                        "state": status.display_state.value,
                        "confidence": status.confidence,
                        "as_of": status.as_of.isoformat(),
                        "source_kind": status.source_kind.value,
                    }
                )
            },
        )
        changed += 1
    return DecayReport(checked=len(rows), changed=changed)


def sweep_stale_feeds(session: Session) -> dict[str, int]:
    """Missing heartbeat for 3 × ttl → the feed's spots go `unknown` (docs/06)."""
    result: dict[str, int] = {}
    for feed in session.execute(text(_FEED_STALE_SQL)).all():
        rows = session.execute(text(_FEED_SPOTS_UNKNOWN_SQL), {"feed_id": feed.id}).scalars().all()
        result[feed.id] = len(rows)
        logger.warning(
            "flux %s silencieux (ttl=%ss) → %d spots inconnus", feed.id, feed.ttl_seconds, len(rows)
        )
    return result


def reset_feed_counters(session: Session) -> None:
    session.execute(
        text(
            "UPDATE feed SET accepted_24h = 0, rejected_24h = 0 "
            "WHERE last_seen_at IS NULL OR last_seen_at < now() - interval '24 hours'"
        )
    )


@app.command()
def once() -> None:
    """One pass of every job — what CI and the smoke tests call."""
    with sync_session() as session:
        decay = recompute_decay(session)
        stale = sweep_stale_feeds(session)
        reset_feed_counters(session)
        session.commit()
    typer.echo(json.dumps({"decay": decay.__dict__, "stale_feeds": stale}, ensure_ascii=False))


@app.command()
def run(
    decay_seconds: int = 60,
    feed_seconds: int = 120,
    weather_minutes: int = 60,
    tide_hours: int = 24,
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    scheduler = BlockingScheduler(timezone="UTC")

    def _decay() -> None:
        with sync_session() as session:
            report = recompute_decay(session)
            session.commit()
        if report.changed:
            logger.info("decay: %d statuts recalculés", report.changed)

    def _feeds() -> None:
        with sync_session() as session:
            sweep_stale_feeds(session)
            reset_feed_counters(session)
            session.commit()

    def _weather() -> None:
        logger.info("weather: %s", refresh_weather())

    def _tides() -> None:
        logger.info("tides: %s", refresh_tides())

    scheduler.add_job(_decay, "interval", seconds=decay_seconds, next_run_time=_now())
    scheduler.add_job(_feeds, "interval", seconds=feed_seconds)
    scheduler.add_job(_weather, "interval", minutes=weather_minutes)
    scheduler.add_job(_tides, "interval", hours=tide_hours)
    logger.info("status worker démarré")
    scheduler.start()


def _now() -> datetime:
    return datetime.now(UTC) + timedelta(seconds=2)


if __name__ == "__main__":  # pragma: no cover
    app()
