"""Bake `data/*.parquet` into the GeoJSON files the browser fetches once.

    uv run python -m app.build_static

Why not hand the frames straight to pydeck: Streamlit inlines a layer's data into the deck
spec and pushes the whole spec over the websocket on *every* rerun. At Bretagne scale that is
4.6 MB per pill toggle, which browns out Streamlit Community Cloud and ends in a connection
error. Served as static files the payload is a URL, the browser caches it, and a rerun costs
a few kilobytes. Colours, radii and tooltips are precomputed here so no per-rerun work is left.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from app.data import DATA_DIR, KIND_LABELS, LAYERS, MARK_COLOURS

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
logger = logging.getLogger("build_static")


def _colour(row: pd.Series) -> list[int]:
    """A green lateral buoy is green on the map: the mark's own colour beats a layer palette."""
    if row["balise"] == "nav_aid" and isinstance(row["colour"], str):
        first = row["colour"].split(",")[0].strip().lower()
        if first in MARK_COLOURS:
            return list(MARK_COLOURS[first])
    return list(LAYERS[str(row["balise"])].colour)


def _tip(row: pd.Series) -> str:
    kind = row.get("kind")
    label = (
        KIND_LABELS[kind]
        if isinstance(kind, str) and kind in KIND_LABELS
        else LAYERS[str(row["balise"])].short
    )
    extra = [
        str(row[field])
        for field in ("category", "colour", "shape")
        if isinstance(row.get(field), str) and row[field]
    ]
    return " · ".join([label, *extra])


def _feature(row: pd.Series, geometry: dict[str, Any]) -> dict[str, Any]:
    name = row["name"]
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "uid": row["uid"],
            "name": str(name) if pd.notna(name) else "Sans nom",
            "tip": _tip(row),
            "fill": _colour(row),
            "radius": LAYERS[str(row["balise"])].radius_m,
        },
    }


def _collection(features: list[dict[str, Any]]) -> str:
    return json.dumps(
        {"type": "FeatureCollection", "features": features},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _points(frame: pd.DataFrame) -> str:
    return _collection(
        [
            _feature(
                row, {"type": "Point", "coordinates": [round(row["lon"], 5), round(row["lat"], 5)]}
            )
            for _, row in frame.iterrows()
        ]
    )


def _polygons(frame: pd.DataFrame) -> str:
    return _collection(
        [
            _feature(
                row,
                {
                    "type": "Polygon",
                    "coordinates": [
                        [[round(x, 5), round(y, 5)] for x, y in json.loads(row["polygon"])]
                    ],
                },
            )
            for _, row in frame.iterrows()
        ]
    )


#: Every file the map can ask for, so the static build and the inline fallback cannot drift.
COLLECTIONS = ("nav_aid", "spot", "spot-visitors", "harbour", "field")


def collection_for(name: str) -> str:
    """The GeoJSON of one collection, built from the Parquet tables."""
    if name == "field":
        return _polygons(pd.read_parquet(DATA_DIR / "areas.parquet"))
    points = pd.read_parquet(DATA_DIR / "points.parquet")
    if name == "spot-visitors":
        return _points(points[(points["balise"] == "spot") & (points["visitor"].eq(True))])
    return _points(points[points["balise"] == name])


def build() -> dict[str, int]:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    return {name: _write(f"{name}.geojson", collection_for(name)) for name in COLLECTIONS}


def _write(name: str, payload: str) -> int:
    path = STATIC_DIR / name
    path.write_text(payload, encoding="utf-8")
    return path.stat().st_size


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    for name, size in build().items():
        logger.info("static/%s.geojson — %d kB", name, size // 1024)


if __name__ == "__main__":
    main()
