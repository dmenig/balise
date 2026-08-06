"""MBFS v0.1 validator (ADR-0004) — MIT-licensed, this is the partnership sales tool.

A vendor runs `uv run balise-mbfs validate https://…/station_status.json` and gets a verdict
before ever talking to us.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx
from balise_api.schemas.feeds import MBFS_VERSION, MbfsSnapshot
from pydantic import ValidationError

Severity = Literal["error", "warning"]
MAX_CLOCK_SKEW = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class Finding:
    severity: Severity
    path: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.path}: {self.message}"


def validate_payload(payload: dict[str, Any], now: datetime | None = None) -> list[Finding]:
    now = now or datetime.now(UTC)
    findings: list[Finding] = []
    try:
        document = MbfsSnapshot.model_validate(payload)
    except ValidationError as error:
        return [
            Finding("error", ".".join(str(part) for part in item["loc"]), item["msg"])
            for item in error.errors()
        ]

    if document.version != MBFS_VERSION:
        findings.append(
            Finding("warning", "version", f"version {document.version!r}, attendu {MBFS_VERSION!r}")
        )
    age = now - document.last_updated
    if age > MAX_CLOCK_SKEW:
        findings.append(
            Finding(
                "error", "last_updated", f"document périmé de {age} — vérifiez l'horloge/le cron"
            )
        )
    if age < -MAX_CLOCK_SKEW:
        findings.append(Finding("error", "last_updated", "horodatage dans le futur"))

    for harbour_index, harbour in enumerate(document.data.harbours):
        base = f"data.harbours[{harbour_index}]"
        if not harbour.fields:
            findings.append(Finding("warning", base, "aucun `field` — le port n'apparaîtra pas"))
        for field_index, field in enumerate(harbour.fields):
            path = f"{base}.fields[{field_index}]"
            findings.extend(_validate_field(path, field, now))
    if not findings:
        findings.append(Finding("warning", "", "document valide — prêt pour un test d'intégration"))
    return findings


def _validate_field(path: str, field: Any, now: datetime) -> list[Finding]:
    findings: list[Finding] = []
    if field.num_free is None and not field.spots:
        findings.append(
            Finding("error", path, "ni `num_free` ni `spots`: aucune information de disponibilité")
        )
    if (
        field.capacity is not None
        and field.num_free is not None
        and field.num_free > field.capacity
    ):
        findings.append(
            Finding("error", f"{path}.num_free", f"{field.num_free} > capacity {field.capacity}")
        )
    if (
        field.visitor_capacity is not None
        and field.capacity is not None
        and field.visitor_capacity > field.capacity
    ):
        findings.append(Finding("error", f"{path}.visitor_capacity", "supérieure à `capacity`"))
    codes = [spot.spot_id for spot in field.spots]
    if len(codes) != len(set(codes)):
        findings.append(Finding("error", f"{path}.spots", "`spot_id` dupliqué dans le field"))
    for spot_index, spot in enumerate(field.spots):
        if spot.observed_at is not None and spot.observed_at - now > MAX_CLOCK_SKEW:
            findings.append(
                Finding("error", f"{path}.spots[{spot_index}].observed_at", "dans le futur")
            )
        if spot.until is not None and spot.until < now:
            findings.append(
                Finding("warning", f"{path}.spots[{spot_index}].until", "réservation déjà expirée")
            )
    return findings


def validate_document(target: str, now: datetime | None = None) -> list[Finding]:
    """`target` is a URL or a local file path."""
    if target.startswith(("http://", "https://")):
        response = httpx.get(target, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    else:
        payload = json.loads(Path(target).read_text(encoding="utf-8"))
    return validate_payload(payload, now)
