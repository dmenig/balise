"""The deck.gl scene.

Every layer's `data` is a URL under Streamlit's static server, never a DataFrame. That keeps
the deck spec — which Streamlit re-sends on every rerun — at a few kilobytes instead of the
4.6 MB the inlined frames cost, and lets the browser cache the geometry across reruns.
See `app.build_static` for how the files are baked.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pydeck as pdk
import streamlit as st

from app.data import LAYERS

#: The picking layers, in draw order: harbours' large discs sit above the balisage.
POINT_LAYERS = ("nav_aid", "spot", "harbour")
AREAS_LAYER = "field"


def static_url() -> str:
    """Streamlit serves `static/` at `<baseUrlPath>/app/static`.

    The prefix is empty on Community Cloud and on a plain `streamlit run`, but a reverse proxy
    can mount the app under a path — reading it back beats hard-coding a leading slash that
    would 404 there and leave the map blank.
    """
    base = str(st.get_option("server.baseUrlPath") or "").strip("/")
    return f"/{base}/app/static" if base else "/app/static"


@dataclass(frozen=True, slots=True)
class View:
    longitude: float
    latitude: float
    zoom: float


def _source(key: str, visitor_only: bool) -> str:
    name = "spot-visitors" if key == "spot" and visitor_only else key
    return f"{static_url()}/{name}.geojson"


def _points_layer(key: str, visitor_only: bool, night: bool) -> pdk.Layer:
    return pdk.Layer(
        "GeoJsonLayer",
        id=key,
        data=_source(key, visitor_only),
        filled=True,
        stroked=True,
        get_fill_color="properties.fill",
        get_point_radius="properties.radius",
        # `pointType: 'circle'` and `pointRadiusUnits: 'meters'` are deck.gl defaults, and pydeck
        # would rewrite those literals into `@@=` accessor expressions if we passed them.
        point_radius_min_pixels=2.5,
        point_radius_max_pixels=16,
        get_line_color=[8, 20, 32, 200] if night else [255, 255, 255, 190],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    )


def _areas_layer() -> pdk.Layer:
    fill = list(LAYERS["field"].colour)
    return pdk.Layer(
        "GeoJsonLayer",
        id=AREAS_LAYER,
        data=f"{static_url()}/{AREAS_LAYER}.geojson",
        filled=True,
        stroked=True,
        get_fill_color=[*fill, 55],
        get_line_color=[*fill, 200],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    )


def _highlight(record: pd.Series | None, night: bool) -> list[pdk.Layer]:
    """A ring around the current pick, so the sheet and the map never disagree about what's open."""
    if record is None:
        return []
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
            get_line_color=[92, 192, 255] if night else [15, 111, 184],
            line_width_min_pixels=3,
            pickable=False,
        )
    ]


def build(
    active: tuple[str, ...],
    visitor_only: bool,
    view: View,
    night: bool,
    selected: pd.Series | None = None,
) -> pdk.Deck:
    layers: list[pdk.Layer] = []
    if AREAS_LAYER in active:
        layers.append(_areas_layer())
    layers.extend(_points_layer(key, visitor_only, night) for key in POINT_LAYERS if key in active)
    layers.extend(_highlight(selected, night))
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
