"""The floating chrome: search bar, detail sheet, legend, disclaimer."""

from __future__ import annotations

import html

import pandas as pd
import pydeck as pdk
import streamlit as st

from app.data import LAYERS, Dataset, Destination, Filters, label_for, search_index
from app.deck import static_is_served, static_url

DISCLAIMER = (
    "<b>Ne pas utiliser pour la navigation.</b> Référentiel indicatif : les cartes officielles "
    "à jour restent obligatoires, et la disponibilité d'une place n'est pas connue."
)
ATTRIBUTION = (
    "Fond de carte © OpenStreetMap / CARTO · Balisage et ports : Shom (Licence Ouverte 2.0) · "
    "Mouillages : OpenStreetMap / OpenSeaMap (ODbL 1.0)"
)

DETAIL_ROWS: tuple[tuple[str, str], ...] = (
    ("category", "Catégorie"),
    ("colour", "Couleur"),
    ("shape", "Forme"),
    ("topmark", "Voyant"),
    ("light", "Feu"),
    ("depth_m", "Profondeur"),
    ("max_loa_m", "Longueur max"),
    ("max_draft_m", "Tirant d'eau max"),
    ("holding", "Tenue"),
    ("capacity", "Capacité"),
    ("visitor_capacity", "Places visiteurs"),
    ("operator", "Gestionnaire"),
    ("vhf_channel", "VHF"),
    ("phone", "Téléphone"),
    ("opening_hours", "Horaires"),
    ("services", "Services"),
    ("price_note", "Tarifs"),
)


def topbar() -> tuple[Filters, Destination | None]:
    """Returns the destination the moment a suggestion is chosen — no Enter needed."""
    index = search_index()
    with st.container(key="topbar"):
        label = st.selectbox(
            "Recherche",
            options=list(index),
            index=None,
            key="query",
            placeholder="Rechercher un port, une ville, une île…",
            label_visibility="collapsed",
        )
        chosen = st.pills(
            "Couches",
            options=list(LAYERS),
            default=list(LAYERS),
            selection_mode="multi",
            format_func=lambda key: LAYERS[key].short,
            key="layers",
            label_visibility="collapsed",
        )
        visitor = st.checkbox("Places visiteurs uniquement", key="visitor")
    return Filters(layers=tuple(chosen or LAYERS), visitor_only=visitor), index.get(label or "")


def _row(label: str, value: object) -> str:
    return f'<div class="sheet-row"><dt>{label}</dt><dd>{html.escape(str(value))}</dd></div>'


def _detail(record: pd.Series) -> str:
    rows = "".join(
        _row(label, record[column])
        for column, label in DETAIL_ROWS
        if column in record.index and pd.notna(record[column]) and record[column] != ""
    )
    website = record.get("website")
    link = (
        f'<div class="sheet-row"><dt>Site</dt><dd>'
        f'<a href="{html.escape(str(website))}" target="_blank">ouvrir</a></dd></div>'
        if isinstance(website, str) and website.startswith("http")
        else ""
    )
    return (
        f'<div class="sheet-kicker">{html.escape(label_for(record))}</div>'
        f'<div class="sheet-title">{html.escape(str(record["name"] or "Sans nom"))}</div>'
        f"<dl>{rows}{link}</dl>"
        f'<div class="note" style="margin-top:8px">{record["lat"]:.5f}, {record["lon"]:.5f}'
        f" · source {html.escape(str(record['source_id']))}</div>"
    )


def _summary(shown: int, total: int) -> str:
    return (
        f'<div class="count"><b>{shown:,}</b> objets affichés sur {total:,} '
        "recensés en Bretagne</div>".replace(",", " ")
    )


def sheet(dataset: Dataset, selected: pd.Series | None, shown: int) -> bool:
    """The bottom sheet. Returns True when the sailor closes the open detail."""
    closed = False
    with st.container(key="sheet"):
        if selected is not None:
            st.markdown(_detail(selected), unsafe_allow_html=True)
            closed = st.button("Fermer", key="close")
        else:
            st.markdown(_summary(shown, dataset.total), unsafe_allow_html=True)
            st.markdown(
                '<div class="note" style="margin-top:6px">Touchez un objet sur la carte pour ses '
                "détails, ou cherchez un port ci-dessus.</div>",
                unsafe_allow_html=True,
            )
        # On a phone the top-right panel is folded away, so the disclaimer rides in the sheet.
        st.markdown(
            f'<div class="note mobile-only" style="margin-top:8px">{DISCLAIMER}</div>',
            unsafe_allow_html=True,
        )
    return closed


def legend() -> bool:
    """Returns True when the sailor asks to go back to the whole-Bretagne view."""
    with st.container(key="legend"):
        lines = "".join(
            f'<div class="legend-line"><span class="dot" style="background:rgb'
            f'{layer.colour}"></span>{html.escape(layer.short)}</div>'
            for layer in LAYERS.values()
        )
        st.markdown(lines, unsafe_allow_html=True)
        home = st.button("Vue d'ensemble", key="home")
        st.checkbox("Mode nuit", key="night")
    return home


def diagnostics(dataset: Dataset) -> None:
    """`?debug=1` — what the host is actually doing, for when the app misbehaves remotely."""
    if not st.query_params.get("debug"):
        return
    served = static_is_served()
    rows = {
        "streamlit": st.__version__,
        "pydeck": pdk.__version__,
        "pandas": pd.__version__,
        "static servi": f"{served} ({static_url()})",
        "mode carte": "fichiers statiques" if served else "données en ligne (repli)",
        "config.toml lu": st.get_option("theme.primaryColor") == "#0f6fb8",
        "thème visiteur": getattr(getattr(st.context, "theme", None), "type", "?"),
        "objets": dataset.total,
    }
    with st.container(key="debug"):
        st.markdown(
            '<div class="note"><b>Diagnostic</b></div>'
            + "".join(f'<div class="note">{k} : <b>{v}</b></div>' for k, v in rows.items()),
            unsafe_allow_html=True,
        )


def footnote() -> None:
    with st.container(key="footnote"):
        st.markdown(
            f'<div class="note">{DISCLAIMER}</div>'
            f'<div class="note" style="margin-top:6px;font-size:10px">{ATTRIBUTION}</div>',
            unsafe_allow_html=True,
        )
