"""`balise-ais-listener` — T3 occupancy *hints* from AIS (docs/06 §T3).

Deliberately weak: most pleasure boats under 15 m carry no AIS. This tier is worthless for a 9 m
sailboat and useful for large `coffres` and Med marinas. It never produces a displayed "free",
and MMSI is hashed, kept 24 h, never shown — vessel identity is not a feature (docs/04 §4).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import typer
import websockets
from balise_api.config import get_settings
from balise_api.db import sync_session
from balise_api.domain.enums import SourceKind, SpotState
from balise_api.services.availability.status import BASE_TRUST
from sqlalchemy import text
from sqlalchemy.orm import Session

app = typer.Typer(add_completion=False, help="Écouteur AIS (indices d'occupation)")
logger = logging.getLogger("balise_workers.ais")

AT_REST_SPEED_KT = 0.5
AT_REST_MINUTES = 15
SNAP_RADIUS_M = 30.0
MMSI_RETENTION = timedelta(hours=24)

#: bbox per coastal region: [[lat_min, lon_min], [lat_max, lon_max]] (aisstream order)
REGIONS: dict[str, list[list[float]]] = {
    "manche": [[48.2, -5.2], [51.2, 2.6]],
    "atlantique": [[43.2, -5.2], [48.6, -0.9]],
    "mediterranee": [[41.2, 2.9], [43.9, 7.7]],
    "corse": [[41.3, 8.4], [43.1, 9.7]],
}

_SNAP_SQL = """
SELECT s.id, s.kind::text AS kind
FROM spot s
WHERE s.active
  AND ST_DWithin(s.geom::geography,
                 ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius)
ORDER BY s.geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
LIMIT 1
"""

_INSERT_SQL = """
INSERT INTO observation (spot_id, state, source_kind, source_ref, observed_at, confidence, payload)
VALUES (:spot_id, CAST(:state AS spot_state), 'ais', :source_ref, :observed_at, :confidence,
        CAST(:payload AS jsonb))
"""

_PURGE_SQL = """
UPDATE observation SET source_ref = NULL
WHERE source_kind = 'ais' AND source_ref IS NOT NULL
  AND received_at < now() - interval '24 hours'
"""


def hash_mmsi(mmsi: str) -> str:
    salt = get_settings().device_token_salt.encode()
    return hashlib.sha256(salt + str(mmsi).encode()).hexdigest()[:32]


@dataclass
class VesselTracker:
    """A vessel is *at rest* below 0.5 kt for ≥ 15 min (docs/06)."""

    since: dict[str, datetime] = field(default_factory=dict)
    emitted: dict[str, datetime] = field(default_factory=dict)

    def at_rest(self, mmsi: str, speed_kt: float, at: datetime) -> bool:
        if speed_kt >= AT_REST_SPEED_KT:
            self.since.pop(mmsi, None)
            return False
        first = self.since.setdefault(mmsi, at)
        if at - first < timedelta(minutes=AT_REST_MINUTES):
            return False
        last = self.emitted.get(mmsi)
        if last is not None and at - last < timedelta(minutes=AT_REST_MINUTES):
            return False
        self.emitted[mmsi] = at
        return True


def record_hint(session: Session, lon: float, lat: float, mmsi: str, at: datetime) -> int | None:
    row = session.execute(
        text(_SNAP_SQL), {"lon": lon, "lat": lat, "radius": SNAP_RADIUS_M}
    ).one_or_none()
    if row is None:
        return None
    session.execute(
        text(_INSERT_SQL),
        {
            "spot_id": row.id,
            "state": SpotState.OCCUPIED.value,
            "source_ref": hash_mmsi(mmsi),
            "observed_at": at,
            "confidence": BASE_TRUST[SourceKind.AIS],
            "payload": json.dumps({"report_kind": "ais_at_rest"}),
        },
    )
    return int(row.id)


async def listen(regions: list[str], stop_after: int | None = None) -> int:
    settings = get_settings()
    if not settings.ais_enabled:
        logger.info("AIS désactivé (FEATURE_AIS / AISSTREAM_API_KEY) — rien à écouter")
        return 0
    subscription = {
        "APIKey": settings.aisstream_api_key,
        "BoundingBoxes": [REGIONS[region] for region in regions],
        "FilterMessageTypes": ["PositionReport"],
    }
    tracker = VesselTracker()
    emitted = 0
    async with websockets.connect(settings.aisstream_url) as socket:
        await socket.send(json.dumps(subscription))
        async for raw in socket:
            message = json.loads(raw)
            if message.get("MessageType") != "PositionReport":
                continue
            report = message["Message"]["PositionReport"]
            metadata = message.get("MetaData", {})
            mmsi = str(metadata.get("MMSI") or report.get("UserID"))
            speed = float(report.get("Sog") or 0.0)
            now = datetime.now(UTC)
            if not tracker.at_rest(mmsi, speed, now):
                continue
            with sync_session() as session:
                spot_id = record_hint(
                    session, float(report["Longitude"]), float(report["Latitude"]), mmsi, now
                )
                session.execute(text(_PURGE_SQL))
                session.commit()
            if spot_id is not None:
                emitted += 1
                logger.info("indice AIS: spot %s occupé", spot_id)
            if stop_after is not None and emitted >= stop_after:
                return emitted
    return emitted


@app.command()
def run(
    region: list[str] = typer.Option(list(REGIONS), help="régions côtières à écouter"),
    stop_after: int | None = typer.Option(None, help="s'arrêter après N indices (tests)"),
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    unknown = [name for name in region if name not in REGIONS]
    if unknown:
        raise typer.BadParameter(f"régions inconnues: {', '.join(unknown)}")
    emitted = asyncio.run(_guarded(region, stop_after))
    typer.echo(json.dumps({"emitted": emitted}))


async def _guarded(regions: list[str], stop_after: int | None) -> int:
    with contextlib.suppress(asyncio.CancelledError, KeyboardInterrupt):
        return await listen(regions, stop_after)
    return 0


if __name__ == "__main__":  # pragma: no cover
    app()
