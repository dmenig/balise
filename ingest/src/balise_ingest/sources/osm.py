"""OpenStreetMap / OpenSeaMap — the only source with real mooring-buoy density (docs/03 §B).

Two paths, both producing the same `RawFeature` shape:
  * bulk: Geofabrik `.osm.pbf` filtered with `osmium` (daily, whole France)
  * delta: Overpass over a coastal bbox (hourly, polite)
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from balise_api.config import get_settings

from balise_ingest.records import RawFeature, SourceRecord

FRANCE_BBOX = (41.0, -5.5, 51.5, 10.0)  # south, west, north, east — Overpass order
TIMEOUT = 300.0
ATTEMPTS = 4
RETRY_BASE_SECONDS = 15
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})

SOURCE = SourceRecord(
    id="osm",
    kind="import",
    licence="odbl-1.0",
    attribution="© les contributeurs OpenStreetMap (ODbL 1.0)",
    url="https://www.openstreetmap.org/copyright",
)

_OSMIUM_FILTERS = (
    "n/seamark:type",
    "w/seamark:type",
    "n/leisure=marina",
    "w/leisure=marina",
    "r/leisure=marina",
    "w/man_made=pier",
)

logger = logging.getLogger(__name__)


def _overpass_query(bbox: tuple[float, float, float, float], newer_than: datetime | None) -> str:
    box = ",".join(str(value) for value in bbox)
    newer = f'(newer:"{newer_than.isoformat()}")' if newer_than else ""
    return f"""
    [out:json][timeout:180];
    (
      node["seamark:type"]({box}){newer};
      node["leisure"="marina"]({box}){newer};
      way["leisure"="marina"]({box}){newer};
      way["man_made"="pier"]({box}){newer};
      way["seamark:type"]({box}){newer};
    );
    out center tags;
    """


def fetch_overpass(
    bbox: tuple[float, float, float, float] = FRANCE_BBOX, newer_than: datetime | None = None
) -> list[RawFeature]:
    payload = _post_overpass(_overpass_query(bbox, newer_than))
    features: list[RawFeature] = []
    for element in payload["elements"]:
        tags = element.get("tags") or {}
        if not tags:
            continue
        lon, lat = _element_point(element)
        if lon is None or lat is None:
            continue
        features.append(
            RawFeature(
                external_id=f"{element['type']}/{element['id']}",
                layer="overpass",
                geometry={"type": "Point", "coordinates": [lon, lat]},
                properties=tags,
            )
        )
    logger.info("overpass: %d features", len(features))
    return features


def _post_overpass(query: str) -> dict[str, Any]:
    """The public instance throttles and 504s under load — retry with backoff (docs/10)."""
    settings = get_settings()
    last_error: Exception | None = None
    for attempt in range(ATTEMPTS):
        if attempt:
            sleep_for = RETRY_BASE_SECONDS * 2**attempt
            logger.warning("overpass indisponible, nouvelle tentative dans %ss", sleep_for)
            time.sleep(sleep_for)
        try:
            response = httpx.post(
                settings.overpass_url,
                content=query.encode(),
                headers={"User-Agent": settings.overpass_user_agent},
                timeout=TIMEOUT,
            )
            if response.status_code in RETRYABLE_STATUS:
                last_error = httpx.HTTPStatusError(
                    f"overpass {response.status_code}", request=response.request, response=response
                )
                continue
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            return payload
        except httpx.HTTPError as exc:
            last_error = exc
    raise RuntimeError(
        "Overpass indisponible après plusieurs tentatives — utilisez le chemin .osm.pbf "
        "(`balise-ingest osm full`) ou une instance auto-hébergée"
    ) from last_error


def _element_point(element: dict[str, object]) -> tuple[float | None, float | None]:
    if "lon" in element and "lat" in element:
        return float(element["lon"]), float(element["lat"])  # type: ignore[arg-type]
    center = element.get("center")
    if isinstance(center, dict):
        return float(center["lon"]), float(center["lat"])
    return None, None


def download_pbf(target: Path) -> Path:
    """~4 GB for France. Streamed to disk, resumable by re-running (docs/10)."""
    settings = get_settings()
    target.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", settings.geofabrik_url, follow_redirects=True, timeout=None) as stream:
        stream.raise_for_status()
        with target.open("wb") as handle:
            for chunk in stream.iter_bytes(chunk_size=1 << 20):
                handle.write(chunk)
    return target


def filter_pbf(pbf: Path, workdir: Path) -> Path:
    """`osmium tags-filter` then `osmium export` — same pipeline as docs/10."""
    workdir.mkdir(parents=True, exist_ok=True)
    seamarks = workdir / "seamarks.osm.pbf"
    geojson = workdir / "seamarks.geojsonseq"
    subprocess.run(
        ["osmium", "tags-filter", "--overwrite", str(pbf), *_OSMIUM_FILTERS, "-o", str(seamarks)],
        check=True,
    )
    subprocess.run(
        ["osmium", "export", "--overwrite", str(seamarks), "-f", "geojsonseq", "-o", str(geojson)],
        check=True,
    )
    return geojson


def read_geojsonseq(path: Path) -> list[RawFeature]:
    features: list[RawFeature] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip().lstrip("\x1e")
            if not line:
                continue
            item = json.loads(line)
            properties = item.get("properties") or {}
            identity = properties.get("@id") or properties.get("id")
            if identity is None or not item.get("geometry"):
                continue
            features.append(
                RawFeature(
                    external_id=str(identity),
                    layer="pbf",
                    geometry=item["geometry"],
                    properties={
                        key: value for key, value in properties.items() if not key.startswith("@")
                    },
                )
            )
    logger.info("pbf export: %d features", len(features))
    return features
