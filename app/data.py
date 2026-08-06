"""The dataset the app reads: two Parquet tables built by `balise_ingest.webdata`."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True, slots=True)
class Layer:
    label: str
    short: str
    colour: tuple[int, int, int]
    radius_m: int


LAYERS: dict[str, Layer] = {
    "nav_aid": Layer("Amers et balisage", "Balisage", (216, 78, 66), 34),
    "spot": Layer("Mouillages et corps-morts", "Mouillages", (33, 118, 191), 46),
    "harbour": Layer("Ports et capitaineries", "Ports", (226, 142, 30), 130),
    "field": Layer("Zones de mouillage (ZMEL)", "Zones", (26, 147, 122), 0),
}

KIND_LABELS: dict[str, str] = {
    "mooring_buoy": "Bouée / corps-mort",
    "anchorage": "Zone de mouillage",
    "berth": "Poste à quai",
    "quay": "Quai",
    "pile": "Pieu / duc-d'Albe",
    "pontoon": "Ponton",
    "dry_berth": "Place à terre",
}

#: The real colour of a mark reads better than a per-layer palette: a green lateral buoy is
#: green on the map. Keyed on the first word of the decoded S-57 COLOUR list.
MARK_COLOURS: dict[str, tuple[int, int, int]] = {
    "rouge": (214, 64, 58),
    "vert": (37, 158, 96),
    "jaune": (240, 190, 52),
    "blanc": (247, 247, 245),
    "noir": (38, 44, 54),
    "bleu": (58, 118, 214),
    "orange": (238, 138, 42),
    "gris": (142, 150, 160),
    "brun": (140, 96, 62),
    "ambre": (238, 176, 42),
    "violet": (150, 88, 190),
}


@dataclass(frozen=True, slots=True)
class Dataset:
    points: pd.DataFrame
    areas: pd.DataFrame
    meta: dict[str, str]

    @property
    def total(self) -> int:
        return len(self.points) + len(self.areas)


@dataclass(frozen=True, slots=True)
class Filters:
    layers: tuple[str, ...]
    visitor_only: bool


@st.cache_data(show_spinner=False)
def load() -> Dataset:
    points = pd.read_parquet(DATA_DIR / "points.parquet")
    areas = pd.read_parquet(DATA_DIR / "areas.parquet")
    meta = json.loads((DATA_DIR / "meta.json").read_text(encoding="utf-8"))
    return Dataset(points=points, areas=areas, meta=meta)


def apply_filters(frame: pd.DataFrame, filters: Filters) -> pd.DataFrame:
    if frame.empty:
        return frame
    mask = frame["balise"].isin(filters.layers)
    if filters.visitor_only and "visitor" in frame.columns:
        # Every spot carries `visitor`; marks and harbours do not, and stay on as landmarks.
        mask &= frame["visitor"].isna() | frame["visitor"].eq(True)
    return frame[mask]


def search(dataset: Dataset, query: str, limit: int = 8) -> pd.DataFrame:
    """Named objects matching a free-text query, ports first — they are what people look for."""
    if not query.strip():
        return dataset.points.head(0)
    frame = pd.concat([dataset.points, dataset.areas.drop(columns=["polygon"])])
    hits = frame[frame["name"].str.contains(query.strip(), case=False, na=False, regex=False)]
    order = hits["balise"].map({"harbour": 0, "field": 1, "spot": 2, "nav_aid": 3}).fillna(4)
    return hits.assign(_rank=order).sort_values(["_rank", "name"]).head(limit)


def label_for(row: pd.Series) -> str:
    kind = row.get("kind")
    if isinstance(kind, str) and kind in KIND_LABELS:
        return KIND_LABELS[kind]
    return LAYERS[str(row["balise"])].label
