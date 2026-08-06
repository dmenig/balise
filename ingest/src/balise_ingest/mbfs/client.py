"""MBFS reference client (ADR-0004): poll a vendor document, or push to Balise.

MIT-licensed on purpose — a vendor should be able to copy this file into their codebase.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from balise_api.schemas.feeds import MbfsSnapshot

logger = logging.getLogger(__name__)
DEFAULT_TIMEOUT = 30.0


@dataclass(frozen=True, slots=True)
class PullResult:
    snapshot: MbfsSnapshot
    fetched_at: datetime
    stale: bool


@dataclass(frozen=True, slots=True)
class MbfsClient:
    base_url: str
    feed_id: str
    token: str
    timeout: float = DEFAULT_TIMEOUT

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    def push_snapshot(self, snapshot: MbfsSnapshot) -> dict[str, object]:
        response = httpx.put(
            f"{self.base_url}/v1/feeds/{self.feed_id}/snapshot",
            content=snapshot.model_dump_json(),
            headers=self._headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return dict(response.json())

    def push_observations(self, observations: list[dict[str, object]]) -> dict[str, object]:
        response = httpx.post(
            f"{self.base_url}/v1/feeds/{self.feed_id}/observations",
            json={"observations": observations},
            headers=self._headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return dict(response.json())

    def health(self) -> dict[str, object]:
        response = httpx.get(
            f"{self.base_url}/v1/feeds/{self.feed_id}/health",
            headers=self._headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return dict(response.json())


def poll_feed(url: str, timeout: float = DEFAULT_TIMEOUT) -> PullResult:
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    snapshot = MbfsSnapshot.model_validate(response.json())
    now = datetime.now(UTC)
    age = (now - snapshot.last_updated).total_seconds()
    return PullResult(snapshot=snapshot, fetched_at=now, stale=age > 3 * snapshot.ttl)


def push_observations(
    base_url: str, feed_id: str, token: str, observations: list[dict[str, object]]
) -> dict[str, object]:
    return MbfsClient(base_url=base_url, feed_id=feed_id, token=token).push_observations(
        observations
    )
