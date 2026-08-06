"""Balise — carte des mouillages, ports et balisage de Bretagne.

Reads the two Parquet tables in `data/` for search and detail, and points deck.gl at the
prebuilt GeoJSON in `static/` for the map itself: no PostGIS, no API, no network, so it
deploys as-is on Streamlit Community Cloud. The full product (docs/07) stays FastAPI +
PostGIS + the MapLibre PWA; this is the map-first shop window on the référentiel.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import panels
from app.data import Dataset, apply_filters, load
from app.deck import AREAS_LAYER, POINT_LAYERS, View, build
from app.theme import css

HOME = View(longitude=-3.4, latitude=48.05, zoom=7.3)
FOCUS_ZOOM = 14.0


def _row_for(dataset: Dataset, uid: str) -> pd.Series | None:
    frame = pd.concat([dataset.points, dataset.areas.drop(columns=["polygon"])])
    hit = frame[frame["uid"] == uid]
    return None if hit.empty else hit.iloc[0]


def _picked_uid(event: object) -> str | None:
    """deck.gl hands the clicked GeoJSON feature back through the widget state, per layer id."""
    objects = getattr(getattr(event, "selection", None), "objects", None)
    if not isinstance(objects, dict):
        return None
    for layer in (*POINT_LAYERS, AREAS_LAYER):
        picked = objects.get(layer)
        if picked:
            properties = picked[0].get("properties", picked[0])
            return str(properties["uid"])
    return None


def _select(dataset: Dataset, uid: str, fly: bool) -> None:
    st.session_state["selected"] = uid
    target = _row_for(dataset, uid) if uid else None
    if fly and target is not None:
        st.session_state["view"] = View(
            longitude=float(target["lon"]), latitude=float(target["lat"]), zoom=FOCUS_ZOOM
        )
    st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Balise — mouillages et balisage de Bretagne",
        page_icon="⚓",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    dataset = load()
    night = bool(st.session_state.get("night", False))
    st.markdown(css(night), unsafe_allow_html=True)

    filters, searched = panels.topbar()
    uid = str(st.session_state.get("selected") or "")
    selected = _row_for(dataset, uid) if uid else None

    view: View = st.session_state.get("view", HOME)
    with st.container(key="mapwrap"):
        event = st.pydeck_chart(
            build(filters.layers, filters.visitor_only, view, night, selected),
            key="map",
            on_select="rerun",
            selection_mode="single-object",
            height=900,
        )

    clicked = _picked_uid(event)
    if clicked is not None and clicked != uid:
        _select(dataset, clicked, fly=False)

    # The count still comes from the frames — the map reads the same objects from static files.
    shown = len(apply_filters(dataset.points, filters)) + len(apply_filters(dataset.areas, filters))
    closed = panels.sheet(dataset, selected, shown)
    home = panels.legend()
    panels.footnote()

    if searched and searched != uid:
        _select(dataset, searched, fly=True)
    if closed:
        _select(dataset, "", fly=False)
    if home:
        st.session_state["view"] = HOME
        _select(dataset, "", fly=False)


main()
