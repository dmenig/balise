"""Turn a `make_fixture` extract into the two Parquet tables the Streamlit app reads.

    uv run python -m balise_ingest.webdata --extract build/bretagne.geojson --out data

The extract keeps every S-57 attribute in `raw`; the app needs a dozen columns. Dropping the
rest takes a regional extract from tens of megabytes to a file that fits in git and loads in
one `read_parquet`.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger("webdata")

POINT_COLUMNS = (
    "uid",
    "balise",
    "name",
    "kind",
    "lon",
    "lat",
    "s57_class",
    "category",
    "colour",
    "shape",
    "topmark",
    "light",
    "visitor",
    "depth_m",
    "max_loa_m",
    "max_draft_m",
    "holding",
    "vhf_channel",
    "phone",
    "website",
    "opening_hours",
    "services",
    "price_note",
    "source_id",
)
AREA_COLUMNS = (
    "uid",
    "balise",
    "name",
    "kind",
    "lon",
    "lat",
    "polygon",
    "capacity",
    "visitor_capacity",
    "operator",
    "price_note",
    "source_id",
)


def _row(properties: dict[str, Any]) -> dict[str, Any]:
    services = properties.get("services")
    return {
        "uid": f"{properties['source_id']}:{properties['external_id']}",
        "services": " · ".join(services) if isinstance(services, list) else None,
        **{
            key: properties.get(key)
            for key in POINT_COLUMNS + AREA_COLUMNS
            if key not in ("uid", "services", "lon", "lat", "polygon")
        },
    }


def _centroid(ring: list[list[float]]) -> tuple[float, float]:
    return sum(c[0] for c in ring) / len(ring), sum(c[1] for c in ring) / len(ring)


def convert(extract: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    raw = json.loads(extract.read_text(encoding="utf-8"))
    points: list[dict[str, Any]] = []
    areas: list[dict[str, Any]] = []
    for feature in raw["features"]:
        geometry = feature["geometry"]
        if geometry is None:
            continue
        row = _row(dict(feature["properties"]))
        if geometry["type"] == "Point":
            lon, lat = geometry["coordinates"]
            points.append({**row, "lon": lon, "lat": lat})
            continue
        ring = geometry["coordinates"][0]
        lon, lat = _centroid(ring)
        areas.append({**row, "lon": lon, "lat": lat, "polygon": json.dumps(ring)})
    point_frame = pd.DataFrame(points).reindex(columns=list(POINT_COLUMNS))
    area_frame = pd.DataFrame(areas).reindex(columns=list(AREA_COLUMNS))
    return point_frame, area_frame, dict(raw["meta"])


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("data"))
    arguments = parser.parse_args()

    points, areas, meta = convert(arguments.extract)
    arguments.out.mkdir(parents=True, exist_ok=True)
    points.to_parquet(arguments.out / "points.parquet", index=False, compression="zstd")
    areas.to_parquet(arguments.out / "areas.parquet", index=False, compression="zstd")
    (arguments.out / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("écrit: %d points, %d zones dans %s", len(points), len(areas), arguments.out)


if __name__ == "__main__":
    main()
