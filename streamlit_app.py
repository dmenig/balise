"""Balise — carte des mouillages, ports et balisage de Bretagne.

Reads the two Parquet tables in `data/` directly: no PostGIS, no API, no network, so it
deploys as-is on Streamlit Community Cloud. The full product (docs/07) stays FastAPI +
PostGIS + the MapLibre PWA; this is the map-first shop window on the référentiel.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import panels
from app.data import Dataset, apply_filters, load
from app.deck import AREAS_LAYER, POINTS_LAYER, View, build, prepare, prepare_areas
from app.theme import css

HOME = View(longitude=-3.4, latitude=48.05, zoom=7.3)
FOCUS_ZOOM = 14.0


def _row_for(dataset: Dataset, uid: str) -> pd.Series | None:
    frame = pd.concat([dataset.points, dataset.areas.drop(columns=["polygon"])])
    hit = frame[frame["uid"] == uid]
    return None if hit.empty else hit.iloc[0]


def _picked_uid(event: object) -> str | None:
    """deck.gl hands the clicked row back through the widget state, keyed by layer id."""
    objects = getattr(getattr(event, "selection", None), "objects", None)
    if not isinstance(objects, dict):
        return None
    for layer in (POINTS_LAYER, AREAS_LAYER):
        picked = objects.get(layer)
        if picked:
            return str(picked[0]["uid"])
    return None


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

    filters = panels.topbar()
    points = apply_filters(dataset.points, filters)
    areas = apply_filters(dataset.areas, filters)

    uid = str(st.session_state.get("selected") or "")
    selected = _row_for(dataset, uid) if uid else None

    view: View = st.session_state.get("view", HOME)
    with st.container(key="mapwrap"):
        event = st.pydeck_chart(
            build(prepare(points), prepare_areas(areas), view, night, selected),
            key="map",
            on_select="rerun",
            selection_mode="single-object",
            height=900,
        )

    clicked = _picked_uid(event)
    if clicked is not None and clicked != uid:
        st.session_state["selected"] = clicked
        st.rerun()

    action = panels.sheet(dataset, selected, len(points) + len(areas))
    home = panels.legend()
    panels.footnote()

    if home:
        st.session_state["view"] = HOME
        st.session_state["selected"] = ""
        st.rerun()

    # "" closes the sheet; a uid comes from a search result and is worth moving the camera for.
    if action is not None:
        st.session_state["selected"] = action
        target = _row_for(dataset, action) if action else None
        if target is not None:
            st.session_state["view"] = View(
                longitude=float(target["lon"]), latitude=float(target["lat"]), zoom=FOCUS_ZOOM
            )
        st.rerun()


main()
