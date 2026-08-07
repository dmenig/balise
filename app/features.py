"""The rows deck.gl draws, built once and cached.

Everything the map needs travels inside the deck spec, which Streamlit re-sends on every
rerun — so every byte is paid for repeatedly and the shape matters. Three things keep it
small: marks are grouped into one layer per colour, so the colour and radius are layer
constants rather than per-row fields; a row carries a positional index instead of a 30-character
uid; and coordinates are rounded to the precision the zoom can actually show.

An earlier version fetched this from files under Streamlit's static server, which is far
cheaper per rerun but only works when the host both serves that route *and* lets the browser
reach it. When it doesn't, the map draws an empty basemap and says nothing. A payload that is
merely larger is a better failure than one that is invisible.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from app.data import KIND_LABELS, LAYERS, MARK_COLOURS, load

#: Marks whose S-57 colour we recognise get their own layer; the rest fall back to the palette.
NAV_AID_FALLBACK = "nav_aid"


@dataclass(frozen=True, slots=True)
class Group:
    """One deck layer: a constant colour and radius, and the rows drawn with them."""

    key: str
    colour: tuple[int, int, int]
    radius_m: int
    rows: list[dict[str, Any]]


def _colour_key(row: pd.Series) -> str:
    if row["balise"] == "nav_aid" and isinstance(row["colour"], str):
        first = row["colour"].split(",")[0].strip().lower()
        if first in MARK_COLOURS:
            return first
    return str(row["balise"])


def _caption(row: pd.Series) -> str:
    """One string does for the tooltip: the name if it has one, else what kind of thing it is."""
    name = row["name"]
    if isinstance(name, str) and name:
        return name
    kind = row.get("kind")
    if isinstance(kind, str) and kind in KIND_LABELS:
        return KIND_LABELS[kind]
    return LAYERS[str(row["balise"])].short


@st.cache_data(show_spinner=False)
def point_groups() -> list[Group]:
    points = load().points
    keys = points.apply(_colour_key, axis=1)
    groups: list[Group] = []
    # Draw order: balisage first, then moorings, then harbours on top of both.
    for key in [*sorted(set(keys) - {"spot", "harbour"}), "spot", "harbour"]:
        frame = points[keys == key]
        if frame.empty:
            continue
        balise = str(frame.iloc[0]["balise"])
        groups.append(
            Group(
                key=key,
                colour=MARK_COLOURS.get(key, LAYERS[balise].colour),
                radius_m=LAYERS[balise].radius_m,
                rows=[
                    {
                        "p": [round(row["lon"], 5), round(row["lat"], 5)],
                        "i": index,
                        "n": _caption(row),
                    }
                    for index, (_, row) in zip(frame.index, frame.iterrows(), strict=True)
                ],
            )
        )
    return groups


@st.cache_data(show_spinner=False)
def visitor_indices() -> set[int]:
    points = load().points
    return set(points.index[points["visitor"].eq(True)])


@st.cache_data(show_spinner=False)
def area_rows() -> list[dict[str, Any]]:
    import json

    areas = load().areas
    return [
        {
            # 4 decimals is ~11 m — finer than a zone outline is surveyed to, and 10 % smaller.
            "polygon": [[round(x, 4), round(y, 4)] for x, y in json.loads(row["polygon"])],
            "i": index,
            "n": _caption(row),
        }
        for index, (_, row) in zip(areas.index, areas.iterrows(), strict=True)
    ]
