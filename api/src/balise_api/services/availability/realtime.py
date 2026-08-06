"""Realtime fan-out: status change → Redis pub/sub → websocket subscribers (docs/07, docs/08).

The API also LISTENs on the Postgres channel so a status written by a worker or by the ingest CLI
reaches connected clients without going through the API process.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from balise_api import cache
from balise_api.db import session_scope
from balise_api.domain.observation import DerivedStatus
from balise_api.repositories.protocols import SpotRef

CHANNEL = "balise:status"
PG_CHANNEL = "status_changed"
MAX_BBOX_SPAN_DEG = 1.0
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Bbox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def contains(self, lon: float, lat: float) -> bool:
        return self.min_lon <= lon <= self.max_lon and self.min_lat <= lat <= self.max_lat

    @property
    def too_large(self) -> bool:
        return (
            self.max_lon - self.min_lon > MAX_BBOX_SPAN_DEG
            or self.max_lat - self.min_lat > MAX_BBOX_SPAN_DEG
        )

    @classmethod
    def parse(cls, values: list[float]) -> Bbox:
        if len(values) != 4:
            raise ValueError("bbox must be [min_lon, min_lat, max_lon, max_lat]")
        box = cls(*values)
        if box.min_lon > box.max_lon or box.min_lat > box.max_lat:
            raise ValueError("bbox is inverted")
        return box


def status_message(spot: SpotRef, status: DerivedStatus) -> dict[str, Any]:
    return {
        "type": "status",
        "spot_id": f"spot_{spot.id}",
        "lon": spot.lon,
        "lat": spot.lat,
        "state": status.display_state.value,
        "raw_state": status.state.value,
        "confidence": status.confidence,
        "as_of": status.as_of.astimezone(UTC).isoformat(),
        "source_kind": status.source_kind.value,
    }


class RedisStatusPublisher:
    async def publish(self, spot: SpotRef, status: DerivedStatus) -> None:
        payload = status_message(spot, status)
        try:
            await cache.redis_client().publish(CHANNEL, json.dumps(payload))
            await cache.redis_client().delete(f"status:{spot.id}")
        except Exception:
            logger.warning("status fan-out failed for spot %s", spot.id)


class Hub:
    """One subscription per connection (docs/08). Fan-out is filtered by bbox in-process."""

    def __init__(self) -> None:
        self._subscribers: dict[asyncio.Queue[dict[str, Any]], Bbox] = {}
        self._relay: asyncio.Task[None] | None = None
        self._listener: asyncio.Task[None] | None = None

    @property
    def connections(self) -> int:
        return len(self._subscribers)

    def subscribe(self, bbox: Bbox) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers[queue] = bbox
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.pop(queue, None)

    def dispatch(self, message: dict[str, Any]) -> None:
        lon, lat = message.get("lon"), message.get("lat")
        for queue, bbox in self._subscribers.items():
            if lon is not None and lat is not None and not bbox.contains(lon, lat):
                continue
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(
                    {key: value for key, value in message.items() if key not in {"lon", "lat"}}
                )

    async def start(self) -> None:
        if self._relay is None:
            self._relay = asyncio.create_task(self._pump_redis())
        if self._listener is None:
            self._listener = asyncio.create_task(self._pump_postgres())

    async def stop(self) -> None:
        for task in (self._relay, self._listener):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._relay = None
        self._listener = None

    async def _pump_redis(self) -> None:
        try:
            pubsub = cache.redis_client().pubsub()
            await pubsub.subscribe(CHANNEL)
            async for event in pubsub.listen():
                if event.get("type") != "message":
                    continue
                self.dispatch(json.loads(event["data"]))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("redis relay stopped; websockets degrade to polling")

    async def _pump_postgres(self) -> None:
        """Relay `NOTIFY status_changed` emitted by workers and by the ingest CLI."""
        try:
            async with session_scope() as session:
                connection = await session.connection()
                raw = await connection.get_raw_connection()
                driver = raw.driver_connection
                await session.execute(text(f"LISTEN {PG_CHANNEL}"))
                await session.commit()
                while True:
                    await asyncio.sleep(0.5)
                    for notify in _drain_notifies(driver):
                        payload = json.loads(notify)
                        await cache.redis_client().publish(CHANNEL, json.dumps(payload))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.info("postgres LISTEN relay unavailable")


def _drain_notifies(driver: Any) -> list[str]:
    notifies = getattr(driver, "notifies", None)
    if notifies is None:
        return []
    out: list[str] = []
    for notify in notifies(timeout=0, stop_after=10):
        out.append(notify.payload)
    return out


async def notify_status(session: Any, spot_id: int, status: DerivedStatus) -> None:
    payload = json.dumps(
        {
            "type": "status",
            "spot_id": f"spot_{spot_id}",
            "state": status.display_state.value,
            "confidence": status.confidence,
            "as_of": status.as_of.astimezone(UTC).isoformat(),
            "source_kind": status.source_kind.value,
        }
    )
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"), {"channel": PG_CHANNEL, "payload": payload}
    )


def heartbeat() -> dict[str, str]:
    return {"type": "heartbeat", "at": datetime.now(UTC).isoformat()}


hub = Hub()
