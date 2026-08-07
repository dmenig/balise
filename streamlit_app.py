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
from app.deck import View, build, layer_ids
from app.theme import css

HOME = View(longitude=-3.4, latitude=48.05, zoom=7.3)


def _viewer_prefers_dark() -> bool:
    theme = getattr(st.context, "theme", None)
    return str(getattr(theme, "type", "light")) == "dark"


def _row_for(dataset: Dataset, uid: str) -> pd.Series | None:
    frame = pd.concat([dataset.points, dataset.areas.drop(columns=["polygon"])])
    hit = frame[frame["uid"] == uid]
    return None if hit.empty else hit.iloc[0]


def _uid_at(dataset: Dataset, layer: str, index: int) -> str:
    """Rows travel with their positional index, not a 30-character uid — resolve it here."""
    frame = dataset.areas if layer == "field" else dataset.points
    return str(frame.loc[index, "uid"]) if index in frame.index else ""


def _picked(event: object) -> tuple[str, int] | None:
    """deck.gl hands the clicked GeoJSON feature back through the widget state, per layer id."""
    objects = getattr(getattr(event, "selection", None), "objects", None)
    if not isinstance(objects, dict):
        return None
    for layer in layer_ids():
        picked = objects.get(layer)
        if picked:
            return layer, int(picked[0]["i"])
    return None


def _select(uid: str) -> None:
    st.session_state["selected"] = uid
    st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Balise — mouillages et balisage de Bretagne",
        page_icon="⚓",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    dataset = load()
    if "night" not in st.session_state:
        # Follow whatever theme the viewer put Streamlit in, so the chrome never fights the app.
        st.session_state["night"] = _viewer_prefers_dark()
    night = bool(st.session_state["night"])
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

    # The count comes from the frames; the map draws the same objects from the deck spec.
    shown = len(apply_filters(dataset.points, filters)) + len(apply_filters(dataset.areas, filters))
    closed = panels.sheet(dataset, selected, shown)
    panels.legend()
    panels.diagnostics(dataset)

    # Every widget is instantiated above, before anything can rerun. Streamlit discards the
    # session-state entry of a widget it did not see on a run, so rerunning from the map click
    # — which sits above the legend — used to drop `night` and switch the map back to day.
    # deck.gl keeps the last pick in widget state and hands it back on every rerun, so acting
    # on its mere presence re-opened the sheet the instant "Fermer" closed it. Only a *change*
    # is an event — and a change to nothing means the sailor tapped open water, which closes.
    hit = _picked(event)
    moved = hit != st.session_state.get("last_pick")
    st.session_state["last_pick"] = hit

    if closed:
        _select("")
    # Searching moves the camera and nothing else: whatever layers are on stay on, so the
    # sailor lands on a place with every nearby mark, mooring and zone still drawn. Only a
    # harbour — the most precise thing you can search for — also opens its detail.
    elif searched is not None and st.session_state.get("flown_to") != searched:
        st.session_state["flown_to"] = searched
        st.session_state["view"] = View(searched.lon, searched.lat, searched.zoom)
        st.session_state["selected"] = searched.uid
        st.session_state["search_open"] = False
        st.rerun()
    elif moved:
        _select(_uid_at(dataset, *hit) if hit else "")


main()
