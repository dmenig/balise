"""Immutable, gzipped raw snapshots (docs/10). Conflation rules change; the sources must not
be hammered again to re-derive."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

from balise_api.config import get_settings

from balise_ingest.records import RawFeature

RETENTION_DAYS = 90


def snapshot_dir(source: str, day: str | None = None) -> Path:
    day = day or datetime.now(UTC).date().isoformat()
    return get_settings().raw_dir / source / day


def write(source: str, layer: str, features: list[RawFeature], day: str | None = None) -> Path:
    target = snapshot_dir(source, day)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{layer}.json.gz"
    payload = {
        "source": source,
        "layer": layer,
        "fetched_at": datetime.now(UTC).isoformat(),
        "count": len(features),
        "features": [
            {
                "external_id": feature.external_id,
                "geometry": feature.geometry,
                "properties": feature.properties,
            }
            for feature in features
        ],
    }
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    return path


def read(path: Path) -> list[RawFeature]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    layer = payload["layer"]
    return [
        RawFeature(
            external_id=item["external_id"],
            layer=layer,
            geometry=item["geometry"],
            properties=item["properties"],
        )
        for item in payload["features"]
    ]


def read_dir(directory: Path) -> dict[str, list[RawFeature]]:
    return {
        path.name.removesuffix(".json.gz"): read(path)
        for path in sorted(directory.glob("*.json.gz"))
    }


def latest(source: str) -> Path | None:
    root = get_settings().raw_dir / source
    if not root.exists():
        return None
    days = sorted((path for path in root.iterdir() if path.is_dir()), reverse=True)
    return days[0] if days else None


def prune(source: str, keep_days: int = RETENTION_DAYS) -> list[Path]:
    root = get_settings().raw_dir / source
    if not root.exists():
        return []
    days = sorted((path for path in root.iterdir() if path.is_dir()), reverse=True)
    removed: list[Path] = []
    for stale in days[keep_days:]:
        for item in stale.iterdir():
            item.unlink()
        stale.rmdir()
        removed.append(stale)
    return removed
