"""The deck.gl scene. One picking layer per geometry type, so a click says what was clicked."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd
import pydeck as pdk

from app.data import KIND_LABELS, LAYERS, MARK_COLOURS

POINTS_LAYER = "points"
AREAS_LAYER = "areas"


@dataclass(frozen=True, slots=True)
class View:
    longitude: float
    latitude: float
    zoom: float


def _colour(row: pd.Series) -> list[int]:
    """A green lateral buoy is green on the map: the mark's own colour beats a layer palette."""
    if row["balise"] == "nav_aid" and isinstance(row["colour"], str):
        first = row["colour"].split(",")[0].strip().lower()
        if first in MARK_COLOURS:
            return list(MARK_COLOURS[first])
    return list(LAYERS[str(row["balise"])].colour)


def _tip(row: pd.Series) -> str:
    kind = row.get("kind")
    bits = [
        KIND_LABELS[kind]
        if isinstance(kind, str) and kind in KIND_LABELS
        else LAYERS[str(row["balise"])].short
    ]
    for field in ("category", "colour", "shape"):
        value = row.get(field)
        if isinstance(value, str) and value:
            bits.append(value)
    return " · ".join(bits)


def prepare(points: pd.DataFrame) -> pd.DataFrame:
    """Only what deck.gl needs crosses the wire: the detail panel reads the full frame instead."""
    if points.empty:
        return pd.DataFrame(columns=["uid", "name", "tip", "lon", "lat", "fill", "radius"])
    # Harbours are drawn last so their larger discs sit above the balisage.
    order = points["balise"].map({"nav_aid": 0, "spot": 1, "harbour": 2}).fillna(0)
    frame = points.assign(_order=order).sort_values("_order")
    return pd.DataFrame(
        {
            "uid": frame["uid"],
            "name": frame["name"].fillna("Sans nom"),
            "tip": frame.apply(_tip, axis=1),
            "lon": frame["lon"],
            "lat": frame["lat"],
            "fill": frame.apply(_colour, axis=1),
            "radius": frame["balise"].map({key: layer.radius_m for key, layer in LAYERS.items()}),
        }
    )


def prepare_areas(areas: pd.DataFrame) -> pd.DataFrame:
    if areas.empty:
        return pd.DataFrame(columns=["uid", "name", "tip", "polygon"])
    return pd.DataFrame(
        {
            "uid": areas["uid"],
            "name": areas["name"].fillna("Zone de mouillage"),
            "tip": areas.apply(_tip, axis=1),
            "polygon": areas["polygon"].map(json.loads),
        }
    )


def _highlight(record: pd.Series | None, night: bool) -> list[pdk.Layer]:
    """A ring around the current pick, so the sheet and the map never disagree about what's open."""
    if record is None:
        return []
    ring = [92, 192, 255] if night else [15, 111, 184]
    return [
        pdk.Layer(
            "ScatterplotLayer",
            id="highlight",
            data=[{"lon": float(record["lon"]), "lat": float(record["lat"])}],
            get_position="[lon, lat]",
            get_radius=180,
            radius_min_pixels=13,
            radius_max_pixels=30,
            filled=False,
            stroked=True,
            get_line_color=ring,
            line_width_min_pixels=3,
            pickable=False,
        )
    ]


def build(
    points: pd.DataFrame,
    areas: pd.DataFrame,
    view: View,
    night: bool,
    selected: pd.Series | None = None,
) -> pdk.Deck:
    fill = list(LAYERS["field"].colour)
    layers = [
        pdk.Layer(
            "PolygonLayer",
            id=AREAS_LAYER,
            data=areas,
            get_polygon="polygon",
            get_fill_color=[*fill, 55],
            get_line_color=[*fill, 200],
            line_width_min_pixels=1,
            stroked=True,
            pickable=True,
            auto_highlight=True,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            id=POINTS_LAYER,
            data=points,
            get_position="[lon, lat]",
            get_fill_color="fill",
            get_radius="radius",
            radius_min_pixels=2.5,
            radius_max_pixels=16,
            line_width_min_pixels=1,
            get_line_color=[255, 255, 255, 190] if not night else [8, 20, 32, 200],
            stroked=True,
            pickable=True,
            auto_highlight=True,
        ),
        *_highlight(selected, night),
    ]
    return pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            longitude=view.longitude, latitude=view.latitude, zoom=view.zoom, pitch=0, bearing=0
        ),
        map_provider="carto",
        map_style="dark" if night else "light",
        tooltip={
            "html": "<b>{name}</b><br/>{tip}",
            "style": {
                "backgroundColor": "rgba(10,29,46,0.92)",
                "color": "#fff",
                "fontSize": "12px",
                "borderRadius": "8px",
                "padding": "6px 9px",
            },
        },
    )
