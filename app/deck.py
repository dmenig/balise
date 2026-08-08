"""The deck.gl scene.

Marks are split across one layer per colour so that the colour and radius are layer constants
instead of per-row fields — see `app.features` for why the payload shape matters. Picking
returns the row's positional index, which the caller looks up in the Parquet frame.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pydeck as pdk

from app.data import LAYERS
from app.features import Group, area_rows, point_groups, visitor_indices

AREAS_LAYER = "field"


class CompactDeck(pdk.Deck):  # type: ignore[misc]  # pydeck ships no stubs
    """A Deck that serialises without pretty-printing.

    `pydeck.bindings.json_tools` dumps with `indent=2`, and Streamlit puts that string
    straight into the protobuf it sends (`deck_gl_json_chart.py`: `spec = pydeck_obj.to_json()`).
    At Bretagne scale the indentation alone is 1.8 MB of spaces on the wire per rerun — two
    thirds of the message, carrying nothing.
    """

    def to_json(self) -> str:
        from pydeck.bindings.json_tools import default_serialize

        return json.dumps(self, sort_keys=True, default=default_serialize, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class View:
    longitude: float
    latitude: float
    zoom: float


def _balise_of(group: Group) -> str:
    return group.key if group.key in ("spot", "harbour") else "nav_aid"


def layer_ids() -> list[str]:
    """Every pickable layer id, so a click can be read back whichever layer it landed on."""
    return [group.key for group in point_groups()] + [AREAS_LAYER]


def _points_layer(group: Group, rows: list[dict[str, object]], night: bool) -> pdk.Layer:
    return pdk.Layer(
        "ScatterplotLayer",
        id=group.key,
        data=rows,
        get_position="p",
        get_fill_color=list(group.colour),
        get_radius=group.radius_m,
        radius_min_pixels=3.2,
        radius_max_pixels=17,
        stroked=True,
        get_line_color=[8, 20, 32, 200] if night else [255, 255, 255, 190],
        line_width_min_pixels=1,
        pickable=True,
        # Streamlit already fades everything but the tapped object to 40 % alpha; deck's own
        # hover tint on top of that is one highlight too many, and it is bruise-purple.
        auto_highlight=False,
    )


def _areas_layer() -> pdk.Layer:
    """Filled, never stroked.

    `stroked=True` makes PolygonLayer add a PathLayer sublayer, and past a few hundred
    polygons — Bretagne has 843 — that sublayer silently breaks deck.gl's click picking for
    *the whole scene*: hover still highlights, but a tap returns no object, so nothing on the
    map can be selected any more. A softer fill reads as well as an outline and keeps the tap.
    """
    fill = list(LAYERS["field"].colour)
    return pdk.Layer(
        "PolygonLayer",
        id=AREAS_LAYER,
        data=area_rows(),
        get_polygon="polygon",
        get_fill_color=[*fill, 78],
        stroked=False,
        filled=True,
        pickable=True,
        auto_highlight=False,
    )


def _pin(place: tuple[float, float] | None, night: bool) -> list[pdk.Layer]:
    """A ring on the place the search took you to — the dropped pin, not the current pick.

    Marking the pick instead would put a *changing* layer in the spec, and any change to the
    spec makes the browser rebuild the whole scene: it costs the best part of a second on
    every single tap. The sheet already says what you tapped; the ring says where you asked
    to go, and stays put while you look around.
    """
    if place is None:
        return []
    return [
        pdk.Layer(
            "ScatterplotLayer",
            id="pin",
            data=[{"p": [place[0], place[1]]}],
            get_position="p",
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
    pin: tuple[float, float] | None = None,
) -> pdk.Deck:
    keep = visitor_indices() if visitor_only else None
    layers: list[pdk.Layer] = []
    if AREAS_LAYER in active:
        layers.append(_areas_layer())
    for group in point_groups():
        if _balise_of(group) not in active:
            continue
        # `visitor` only exists on spots; marks and harbours stay on as landmarks.
        rows = (
            [row for row in group.rows if row["i"] in keep]
            if keep is not None and group.key == "spot"
            else group.rows
        )
        layers.append(_points_layer(group, rows, night))
    layers.extend(_pin(pin, night))
    return CompactDeck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            longitude=view.longitude, latitude=view.latitude, zoom=view.zoom, pitch=0, bearing=0
        ),
        map_provider="carto",
        map_style="dark" if night else "light",
        tooltip={
            "html": "<b>{n}</b>",
            "style": {
                "backgroundColor": "rgba(10,29,46,0.92)",
                "color": "#fff",
                "fontSize": "12px",
                "borderRadius": "8px",
                "padding": "6px 9px",
            },
        },
    )
