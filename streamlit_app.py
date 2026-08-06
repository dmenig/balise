"""Balise — visionneuse Streamlit du référentiel (extrait Golfe du Morbihan).

Lit directement la fixture versionnée `ingest/.../morbihan.geojson` : ni base PostGIS ni API,
donc déployable tel quel sur Streamlit Community Cloud. Le produit complet (docs/07) reste
FastAPI + PostGIS + PWA MapLibre ; ceci en est une vitrine en lecture seule.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

FIXTURE = Path(__file__).parent / "ingest/src/balise_ingest/fixtures/morbihan.geojson"

ATTRIBUTION = (
    "Fonds de carte © OpenStreetMap contributors / CARTO — Amers et balisage : Shom, 2026 "
    "(Licence Ouverte Etalab 2.0) — Mouillages : OpenStreetMap/OpenSeaMap (ODbL 1.0)."
)
DISCLAIMER = (
    "**Ne pas utiliser pour la navigation.** Les cartes officielles à jour restent obligatoires ; "
    "ce référentiel est indicatif et ne dit pas si une place est libre (docs/06)."
)


@dataclass(frozen=True)
class LayerStyle:
    label: str
    colour: tuple[int, int, int]
    radius_m: int


STYLES: dict[str, LayerStyle] = {
    "nav_aid": LayerStyle("Amers et balisage (Shom)", (203, 67, 53), 40),
    "spot": LayerStyle("Mouillages et corps-morts", (41, 128, 185), 55),
    "harbour": LayerStyle("Ports et capitaineries", (211, 132, 27), 110),
    "field": LayerStyle("Zones de mouillage (ZMEL)", (39, 132, 108), 0),
}

KIND_LABELS: dict[str, str] = {
    "mooring_buoy": "bouée / corps-mort",
    "anchorage": "zone de mouillage",
}


@st.cache_data(show_spinner=False)
def load_fixture() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str | list[str]]]:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    points: list[dict[str, object]] = []
    polygons: list[dict[str, object]] = []
    for feature in raw["features"]:
        props = dict(feature["properties"])
        geometry = feature["geometry"]
        row: dict[str, object] = {
            "balise": props["balise"],
            "name": props.get("name") or "sans nom",
            "kind": props.get("kind"),
            "source_id": props["source_id"],
            "external_id": props["external_id"],
            "visitor": props.get("visitor"),
            "category": props.get("category"),
            "colour": props.get("colour"),
            "shape": props.get("shape"),
            "topmark": props.get("topmark"),
            "s57_class": props.get("s57_class"),
            "price_note": props.get("price_note"),
        }
        if geometry["type"] == "Point":
            lon, lat = geometry["coordinates"]
            points.append({**row, "lon": lon, "lat": lat})
        else:
            ring = geometry["coordinates"][0]
            centroid_lon = sum(c[0] for c in ring) / len(ring)
            centroid_lat = sum(c[1] for c in ring) / len(ring)
            polygons.append(
                {
                    **row,
                    "polygon": geometry["coordinates"][0],
                    "lon": centroid_lon,
                    "lat": centroid_lat,
                }
            )
    return pd.DataFrame(points), pd.DataFrame(polygons), raw["meta"]


def describe(row: pd.Series) -> str:
    style = STYLES[str(row["balise"])]
    bits: list[str] = [style.label]
    if isinstance(row.get("kind"), str):
        bits.append(KIND_LABELS.get(row["kind"], row["kind"]))
    if isinstance(row.get("category"), str):
        bits.append(f"cardinale/latérale : {row['category']}")
    for field in ("colour", "shape", "topmark"):
        if isinstance(row.get(field), str):
            bits.append(row[field])
    if row.get("visitor") is True:
        bits.append("ouvert aux visiteurs")
    if isinstance(row.get("price_note"), str):
        bits.append(row["price_note"])
    bits.append(f"source : {row['source_id']}")
    return " · ".join(bits)


def sidebar_filters(
    points: pd.DataFrame, polygons: pd.DataFrame
) -> tuple[list[str], list[str], bool, str]:
    st.sidebar.header("Filtres")
    available = [key for key in STYLES if key in set(points["balise"]) | set(polygons["balise"])]
    layers = st.sidebar.multiselect(
        "Couches",
        options=available,
        default=available,
        format_func=lambda key: STYLES[key].label,
    )
    kinds_present = sorted(
        set(points["kind"].dropna().unique()) | set(polygons["kind"].dropna().unique())
    )
    kinds = st.sidebar.multiselect(
        "Type de mouillage",
        options=kinds_present,
        default=kinds_present,
        format_func=lambda key: KIND_LABELS.get(key, key),
    )
    visitor_only = st.sidebar.toggle("Places visiteurs uniquement", value=False)
    query = st.sidebar.text_input("Recherche par nom", placeholder="Kerpenhir, Port Maria…")
    return layers, kinds, visitor_only, query


def apply_filters(
    frame: pd.DataFrame, layers: list[str], kinds: list[str], visitor_only: bool, query: str
) -> pd.DataFrame:
    if frame.empty:
        return frame
    mask = frame["balise"].isin(layers)
    mask &= frame["kind"].isna() | frame["kind"].isin(kinds)
    if visitor_only:
        # `visitor` n'existe que sur les places ; le balisage reste affiché comme repère.
        mask &= frame["visitor"].isna() | frame["visitor"].eq(True)
    if query:
        mask &= frame["name"].str.contains(query, case=False, na=False)
    return frame[mask].copy()


def build_deck(
    points: pd.DataFrame, polygons: pd.DataFrame, meta: dict[str, str | list[str]]
) -> pdk.Deck:
    layers: list[pdk.Layer] = []
    if not polygons.empty:
        polygons = polygons.assign(
            fill=[list(STYLES["field"].colour) for _ in range(len(polygons))]
        )
        layers.append(
            pdk.Layer(
                "PolygonLayer",
                data=polygons,
                get_polygon="polygon",
                get_fill_color="[fill[0], fill[1], fill[2], 60]",
                get_line_color="fill",
                line_width_min_pixels=1,
                pickable=True,
                stroked=True,
            )
        )
    if not points.empty:
        points = points.assign(
            fill=[list(STYLES[b].colour) for b in points["balise"]],
            radius=[STYLES[b].radius_m for b in points["balise"]],
        )
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=points,
                get_position="[lon, lat]",
                get_fill_color="[fill[0], fill[1], fill[2], 210]",
                get_radius="radius",
                radius_min_pixels=3,
                radius_max_pixels=18,
                pickable=True,
            )
        )
    west, south, east, north = (float(v) for v in str(meta["bbox"]).split(","))
    view = pdk.ViewState(
        longitude=(west + east) / 2, latitude=(south + north) / 2, zoom=9.6, pitch=0
    )
    return pdk.Deck(
        layers=layers,
        initial_view_state=view,
        map_provider="carto",
        map_style="light",
        tooltip={"html": "<b>{name}</b><br/>{summary}", "style": {"fontSize": "12px"}},
    )


def main() -> None:
    st.set_page_config(page_title="Balise — référentiel", page_icon="⚓", layout="wide")
    points, polygons, meta = load_fixture()
    points = points.assign(summary=points.apply(describe, axis=1))
    polygons = polygons.assign(summary=polygons.apply(describe, axis=1))

    st.title("⚓ Balise — mouillages, ports et balisage")
    st.caption(
        f"Extrait « {meta['name']} » généré le {str(meta['generated_at'])[:10]} — "
        f"{len(points) + len(polygons)} objets, bbox {meta['bbox']}."
    )
    st.warning(DISCLAIMER)

    layers, kinds, visitor_only, query = sidebar_filters(points, polygons)
    shown_points = apply_filters(points, layers, kinds, visitor_only, query)
    shown_polygons = apply_filters(polygons, layers, kinds, visitor_only, query)

    columns = st.columns(len(STYLES))
    counts = pd.concat([shown_points["balise"], shown_polygons["balise"]]).value_counts()
    for column, (key, style) in zip(columns, STYLES.items(), strict=True):
        column.metric(style.label, int(counts.get(key, 0)))

    st.pydeck_chart(build_deck(shown_points, shown_polygons, meta))

    with st.expander(f"Liste des objets affichés ({len(shown_points) + len(shown_polygons)})"):
        table = pd.concat([shown_points, shown_polygons])[
            ["name", "balise", "kind", "visitor", "source_id", "external_id", "lat", "lon"]
        ]
        st.dataframe(table.reset_index(drop=True), width="stretch", height=420)

    st.divider()
    st.caption(ATTRIBUTION)
    st.caption(
        "Disponibilité (« quelle place est libre ») hors périmètre v1 : aucune source publique "
        "n'existe, la fonctionnalité est câblée derrière six seams — voir docs/06."
    )


main()
