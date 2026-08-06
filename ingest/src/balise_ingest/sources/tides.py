"""SHOM SPM tide predictions (docs/03 §D).

Gated on `SHOM_TIDE_API_KEY`: with no key the tier is simply off — the app must boot and serve the
referential with no third-party credentials at all (docs/11). Redistribution terms are still to be
confirmed (docs/15), which is why nothing here is exposed raw: we serve derived HW/LW only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal

import httpx
from balise_api.config import get_settings

TIMEOUT = 30.0
_KIND_BY_CODE = {"tide.high": "HW", "tide.low": "LW", "tide.none": None}
logger = logging.getLogger(__name__)


class TidesDisabled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TideRow:
    harbour_id: int
    at: datetime
    height_m: Decimal
    kind: str | None
    coefficient: int | None


def _coefficient(raw: str) -> int | None:
    cleaned = raw.strip().replace("---", "")
    return int(cleaned) if cleaned.isdigit() else None


def parse_hlt(payload: dict[str, object], harbour_id: int) -> list[TideRow]:
    """SHOM `hlt` shape: `{"data": {"2026-08-06": [["tide.high","03:12","5.60","78"], …]}}`."""
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("réponse SHOM SPM inattendue: clé 'data' absente")
    rows: list[TideRow] = []
    for day, entries in sorted(data.items()):
        day_date = date.fromisoformat(day)
        for entry in entries:
            code, clock, height, *rest = entry
            kind = _KIND_BY_CODE.get(str(code))
            hour, minute = (int(part) for part in str(clock).split(":")[:2])
            rows.append(
                TideRow(
                    harbour_id=harbour_id,
                    at=datetime.combine(day_date, time(hour, minute), tzinfo=UTC),
                    height_m=Decimal(str(height)),
                    kind=kind,
                    coefficient=_coefficient(str(rest[0])) if rest else None,
                )
            )
    return rows


def fetch_harbour(
    client: httpx.Client, harbour_id: int, spm_key: str, days: int = 7
) -> list[TideRow]:
    settings = get_settings()
    if not settings.tides_enabled:
        raise TidesDisabled("SHOM_TIDE_API_KEY absent — marées désactivées")
    response = client.get(
        settings.shom_tide_api_url,
        params={
            "harborName": spm_key,
            "duration": days,
            "date": datetime.now(UTC).date().isoformat(),
            "utc": "1",
            "correlation": "1",
        },
        headers={"Authorization": f"Bearer {settings.shom_tide_api_key}"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return parse_hlt(response.json(), harbour_id)
