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


#: S-57 LITCHR and COLOUR, as a chart writes them: `Fl(3)R 12s · 4 M`, not a record of codes.
LIGHT_CHARACTER: dict[int, str] = {
    1: "F",
    2: "Fl",
    3: "LFl",
    4: "Q",
    5: "VQ",
    6: "UQ",
    7: "Iso",
    8: "Oc",
    9: "IQ",
    10: "IVQ",
    11: "IUQ",
    12: "Mo",
    13: "FFl",
    25: "Q+LFl",
    26: "VQ+LFl",
    27: "UQ+LFl",
    28: "Al",
}
LIGHT_COLOUR: dict[str, str] = {"1": "W", "3": "R", "4": "G", "5": "Bu", "6": "Y", "10": "Vi"}
#: OpenSeaMap's `seamark:light:colour`, as words, sometimes `;`-separated for a sector light.
OSM_LIGHT_COLOUR: dict[str, str] = {
    "white": "W",
    "red": "R",
    "green": "G",
    "blue": "Bu",
    "yellow": "Y",
    "violet": "Vi",
}
SERVICE_LABELS: dict[str, str] = {
    "pump_out": "Eaux noires",
    "fuel": "Carburant",
    "water": "Eau",
    "electricity": "Électricité",
    "shower": "Douches",
    "toilets": "Toilettes",
    "crane": "Grue",
    "slipway": "Cale",
    "laundry": "Laverie",
    "wifi": "Wi-Fi",
}


def _number(value: object) -> float | None:
    """Shom writes these as numbers, OpenSeaMap as the strings a mapper typed."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def light_of(light: dict[str, object]) -> str:
    """The light's characteristic. Shom fills the S-57 codes, OpenSeaMap the abbreviations."""
    code = _number(light.get("litchr"))
    character = (
        LIGHT_CHARACTER.get(int(code), "")
        if code is not None
        else str(light.get("osm_character") or "")
    )
    group = str(light.get("siggrp") or "").replace("(1)", "")
    colour = LIGHT_COLOUR.get(str(light.get("colour")), "") or "".join(
        OSM_LIGHT_COLOUR.get(word.strip(), "")
        for word in str(light.get("osm_colour") or "").split(";")
    )
    parts = [f"{character}{group}{colour}"]
    period = _number(light.get("sigper")) or _number(light.get("osm_period"))
    if period:
        parts.append(f"{period:g}s")
    nominal_range = _number(light.get("valnmr")) or _number(light.get("osm_range"))
    if nominal_range:
        parts.append(f"{nominal_range:g} M")
    return " ".join(part for part in parts if part)


def services_of(services: str) -> str:
    return ", ".join(SERVICE_LABELS.get(tag, tag) for tag in services.split(";"))


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


@dataclass(frozen=True, slots=True)
class Destination:
    """Somewhere the search box can take you. `uid` is set only for a harbour."""

    lon: float
    lat: float
    zoom: float
    uid: str = ""


#: What you can search for, and how far back the camera pulls. A harbour is as precise as it
#: goes: nobody searches for an individual buoy, and offering 6 500 of them buried the places.
PLACE_KINDS: dict[str, tuple[str, float]] = {
    "city": ("Ville", 11.5),
    "town": ("Ville", 12.5),
    "island": ("Île", 12.0),
    "village": ("Village", 13.5),
}
HARBOUR_ZOOM = 14.5
_ORDER = {"city": 0, "town": 1, "island": 2, "harbour": 3, "village": 4}


@st.cache_data(show_spinner=False)
def search_index() -> dict[str, Destination]:
    """`label -> Destination`, ranked so towns and harbours come before hamlets.

    The whole index goes to the browser once, so the box filters as you type instead of
    waiting for Enter and a server round-trip.
    """
    places = pd.read_parquet(DATA_DIR / "places.parquet")
    harbours = load().points.query("balise == 'harbour'")
    rows = [
        (_ORDER[row["kind"]], str(row["name"]), PLACE_KINDS[row["kind"]][0], row, "")
        for _, row in places.iterrows()
    ] + [
        (_ORDER["harbour"], str(row["name"]), "Port", row, str(row["uid"]))
        for _, row in harbours.iterrows()
        if pd.notna(row["name"])
    ]
    index: dict[str, Destination] = {}
    for _, name, kind, row, uid in sorted(rows, key=lambda item: (item[0], item[1])):
        label = f"{name} · {kind}"
        # Several communes share a name with their harbour; keep both reachable.
        if label in index:
            label = f"{label} ({row['lat']:.3f}, {row['lon']:.3f})"
        zoom = HARBOUR_ZOOM if uid else PLACE_KINDS[row["kind"]][1]
        index[label] = Destination(float(row["lon"]), float(row["lat"]), zoom, uid)
    return index


def label_for(row: pd.Series) -> str:
    kind = row.get("kind")
    if isinstance(kind, str) and kind in KIND_LABELS:
        return KIND_LABELS[kind]
    return LAYERS[str(row["balise"])].label
